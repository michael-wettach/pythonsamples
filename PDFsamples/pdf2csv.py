#!/usr/bin/python3
# pdf2csv.py
# Tested with Python3 and pdfminer.six module
# This link has useful information on components of the program
# https://euske.github.io/pdfminer/programming.html
# http://denis.papathanasiou.org/posts/2010.08.04.post.html

""" Converts a Postbank PDF bank statement to CSV file """

import re   # for regular expressions
import sys  # for argv
from PyPDF2 import PdfFileReader
from collections import deque

from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.layout import LAParams, LTTextBox, LTTextLine
from pdfminer.converter import XMLConverter, HTMLConverter, TextConverter, PDFPageAggregator

from io import StringIO


def convert_pdf_to_txt(path):
    """ This function intends to capture text with lots of white space side by side.
    This is achieved by setting a very wide char margin in LAParams.
    Such parameter settings are needed for bank statements and invoices.
    This code was found at https://stackoverflow.com/questions/51460372/

    Important PDFminer classes to remember:
    PDFParser - fetches data from pdf file
    PDFDocument - stores data parsed by PDFParser
    PDFPageInterpreter - processes page contents from PDFDocument
    PDFDevice - translates processed information from PDFPageInterpreter to whatever you need
    PDFResourceManager - Stores shared resources such as fonts or images used by both PDFPageInterpreter and PDFDevice
    LAParams - A layout analyzer returns a LTPage object for each page in the PDF document
    PDFPageAggregator - Extract the decive to page aggregator to get LT object elements
    """

    rsrcmgr = PDFResourceManager()
    retstr = StringIO()
    codec = 'utf-8'

    """ LAParams Documentation 
        from https://readthedocs.org/projects/pdfminer-docs/downloads/pdf/latest/
        and https://pdfminersix.readthedocs.io/en/latest/api/composable.html
    all_texts
      Forces to perform layout analysis for all the text strings, including text contained in figures.
    detect_vertical
      Allows vertical writing detection.
    line_overlap
      If two characters have more overlap than this they are considered to be on the same line.
      The overlap is specified relative to the minimum height of both characters.
    char_margin, line_margin, word_margin
      These are the parameters used for layout analysis. 
      In an actual PDF file, text portions might be split into several chunks in the middle of its running, 
      depending on the authoring software. Therefore, text extraction needs to splice text chunks.
      Furthermore, it may be required to insert blank characters (spaces) as necessary 
      if the distance between two words is greater than the word_margin, 
      as a blank between words might not be represented as a space, but indicated by the positioning of each word.
      Each value is specified not as an actual length, 
      but as a proportion of the length to the size of each character in question. 
      The default values are char_margin = 2.0, line_margin = 0.5, and word_margin = 0.1, respectively.
    char_margin   
      Two text chunks whose distance is closer than the char_margin is considered continuous and get grouped into one.
      If characters are on the same line but not part of the same word, an intermediate space is inserted. 
      The margin is specified relative to the width of the character.
    line_margin  
      If two lines are close together they are considered to be part of the same paragraph. 
      Two lines whose distance is closer than the line_margin is grouped as a text box, 
      which is a rectangular area that contains a “cluster” of text portions. 
      The margin is specified relative to the height of a line.
    word_margin
      If two words are are closer together than this margin they are considered to be part of the same line. 
      A space is added in between for readability. The margin is specified relative to the width of the word.  
    boxes_flow 
      Specifies how much a horizontal and vertical position of a text matters when determining a text order. 
      Should be within the range of -1.0 (only horizontal position matters) to +1.0 (only vertical position matters). 
      The default value is 0.5.
    """
    laparams = LAParams(all_texts=False, detect_vertical=False,
                        line_overlap=0.3, char_margin=900.0,  # large number
                        line_margin=0.5, word_margin=1.2,
                        boxes_flow=0.7)  # vertical position has priority of 70% in output order
    device = TextConverter(rsrcmgr, retstr, codec=codec, laparams=laparams)
    fp = open(path, 'rb')
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    password = ""
    maxpages = 0
    caching = True
    pagenos = set()

    for page in PDFPage.get_pages(fp, pagenos, maxpages=maxpages, password=password, caching=caching,
                                  check_extractable=True):
        interpreter.process_page(page)

    text = retstr.getvalue()

    fp.close()
    device.close()
    retstr.close()
    return text


def convert_pdf_to_txt_pyPDF(path):
    # This function uses PyPDF instead of PDFminer
    # Returns only empty text lines for BBB bank statements
    pdf = PdfFileReader(open(path, "rb"))
    text = ""
    for page in pdf.pages:
        text += page.extractText()
    return text


def convert_pdf_to_txt_pos(path):
    # Should output text box content together with left upper edge of text box.
    # However, in BBB bank statement all text is "painted" as LTFigure, thus output is empty.
    fp = open(path, 'rb')
    rsrcmgr = PDFResourceManager()
    laparams = LAParams()
    device = PDFPageAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    print(str(sum(1 for _ in PDFPage.get_pages(fp))) + ' pages found.')
    result = ""
    pagenr = 0
    pages = PDFPage.get_pages(fp)
    for mypage in pages:
        pagenr += 1
        print('Processing page ' + str(pagenr))
        interpreter.process_page(mypage)
        layout = device.get_result()
        for lobj in layout:
            if isinstance(lobj, LTTextBox):
                x, y, text = lobj.bbox[0], lobj.bbox[3], lobj.get_text()
                result += 'At ' + str(x) + ',' + str(y) + ' is text: ' + 'text'
    return result


def svl(obj) -> str:
    # Make sure that output is a string
    if obj is None:
        output = ""
    else:
        output = str(obj).strip()
    return output


class pbParser:
    # captures the state of parsing and responds to parsing events
    # author: Michael Wettach, Feb 2020
    # expect_xxx stores the number of unresolved postings
    debugLevel = 1       # if set to 1, we get warnings, if 2 we get infos as well
    page_active = 0   # if set to 1, unexpected text lines will be stored in the queue
    expect_date = 0   # we received a partial posting, but the date is missing
    expect_text = 0   # we received a partial posting, but some text is missing
    expect_cash = 0   # we received a partial posting, but the amount is missing

    # identify different types of lines in the banking statement
    # we do that by regular expressions which are compiled in advance
    full_line = re.compile('^(\d\d\.\d\d\.)\/(\d\d\.\d\d\.)(.+)((\+|\-) ?[\d\.\,]+)')
    part_line = re.compile('^(\d\d\.\d\d\.)\/(\d\d\.\d\d\.)(.+)')
    amount_line = re.compile('(\+|\-) ?[\d\.\,]+')
    text_line = re.compile('\S.+')
    page_nr = re.compile('^\d\d?\/.\d\d?')

    # We need some place to store incomplete postings. deque() is optimized for first-in first-out usage.
    # There will be only one parser, so we can use mutable objects as class variables (normally not recommended)
    # and do not need to instantiate them in the __init__ method.
    dates = deque()
    texts_complete = deque()
    texts_incomplete = deque()
    money = deque()
    text_lines = deque()

    def debug(self, level, myStr):
        # Make sure that output is a string
        if self.debugLevel >= level:
            print(myStr)
        return

    def __init__(self, text):
        self.debug(3, text)
        return

    def receive_date(self, part):
        # the normal sequence is that a date appears as the first item received (i. e. unexpected);
        # in that case we create a new unresolved posting with missing text and amount.
        # receiving a date implies receiving the first line of text as well,
        # but as the line is not complete, we set expectation for further text to come in.
        self.debug(2, "Received part: " + str(part.group(0)))
        self.dates.append('"' + str(part.group(1)) + '";"' + svl(part.group(2)) + '";')
        self.debug(2, "Stored date " + self.dates[-1])
        if self.expect_date == 0:
            # a date was not expected and creates a new posting with incomplete text entry
            self.texts_incomplete.append('"' + svl(part.group(3)))
            self.text_lines.append(1)
            self.debug(2, "Stored text " + self.texts_incomplete[-1])
            self.expect_text += 1
            self.expect_cash += 1
        else:
            # a date was expected, which means we either already have an amount or a text.
            # do we need to create or prepend the text entry?
            self.expect_date -= 1
            prepend = 0
            if len(self.texts_complete) > 0:
                # now this is somewhat clumsy: we look through already completed paragraphs
                # for the first item that hasn't got the date text and thus is missing a hyphen.
                # fortunately there will not be many entries in that list
                for i in range(0, len(self.texts_complete)):
                    if self.texts_complete[i][0] != '"':
                        # there is unfinished text in text_complete, we prepend that and try to print
                        self.texts_complete[i] = '"' + svl(part.group(3)) + ' ' + self.texts_complete[i]
                        self.debug(2, "Prepended text " + svl(part.group(3)))
                        self.queue_pop()
                        prepend = 1
                        break
            if prepend == 0:
                # so we have not been successful in finding a completed paragraph without hyphen
                if len(self.texts_incomplete) == 0 or self.texts_incomplete[0][0] == '"':
                    # there is no text to prepend, so we create a new text
                    self.texts_incomplete.append('"' + svl(part.group(3)))
                    self.text_lines.append(1)
                    self.debug(2, "Stored text " + self.texts_incomplete[-1])
                else:
                    # there is unfinished text in text_incomplete, we prepend that and assume the text is complete now
                    self.texts_incomplete[0] = '"' + svl(part.group(3)) + str(self.texts_incomplete[0])
                    self.text_lines[0] += 1  # expects at least 2
                    self.debug(2, "Prepended text " + svl(part.group(3)))
                    self.receive_blank()
        return

    def receive_text(self, text):
        # we only accept text outside of header and footer, this is indicated by page_active
        if self.page_active > 0:
            if len(self.texts_incomplete) > 0 and self.expect_text > 0:
                # receiving a text when text is expected adds to the first posting present.
                self.texts_incomplete[0] = self.texts_incomplete[0] + " " + str(text.string).strip()
                self.text_lines[0] += 1
                self.debug(2, "Appended text " + str(text.string).strip())
            else:
                # receiving a text when no text is expected means date and cash are missing.
                # in this case we create a new posting and expectations for missing elements.
                self.texts_incomplete.append(str(text.string).strip())
                self.text_lines.append(1)
                self.debug(2, "Stored text " + self.texts_incomplete[-1])
                self.expect_text = 1
                self.expect_date += 1
                self.expect_cash += 1
        return

    def receive_cash(self, amount):
        # add amount to the amount queue
        self.money.append(amount.string.replace(" ", ""))
        self.debug(2, "Stored amount " + self.money[-1])
        if self.expect_cash == 0:
            # receiving an amount when no amount is expected means date and text are missing.
            # in this case we create expectations for date and text
            self.expect_date += 1
            self.expect_text += 1
        else:
            # An amount was expected, so let's try to spool this posting
            self.expect_cash -= 1
            self.queue_pop()
        return

    def receive_blank(self):
        # depending on whether the first posting has already received additional text,
        # a blank line either completes the first posting or is ignored.
        # we cannot flush the complete queue here, but only the first posting
        if len(self.text_lines) > 0 and self.text_lines[0] > 1:
            self.debug(2, "Blank line used to finish current paragraph")
            # move to completed queue
            self.texts_complete.append(self.texts_incomplete.popleft())
            self.text_lines.popleft()
            self.queue_pop()
        else:
            self.debug(2, "***Ignored blank line as there is no complete paragraph yet.")
        return

    def queue_pop(self):
        # at this point we try to print the first queued posting.
        self.debug(2, "Trying to spool first item in queue...")
        if len(self.dates) > 0 and len(self.texts_complete) > 0 and len(self.money) > 0:
            output = str(self.dates.popleft()) + str(self.texts_complete.popleft()).replace("- ", "") + '";"' \
                     + str(self.money.popleft()) + '"'
            print(output)
        else:
            # analytical printout for debug purposes
            if len(self.dates) == 0:
                output = "***Date is missing, "
            else:
                output = "***Date is present, "
            if len(self.texts_complete) == 0:
                output = output + "Text is missing, "
            else:
                output = output + "Text is present, "
            if len(self.money) == 0:
                output = output + "Amount is missing"
            else:
                output = output + "Amount is present"
            self.debug(2, output)
        return

    def queue_flush(self):
        # at this point we do not expect any new data and print everything we have.
        # all variables need to be reset.
        self.debug(2, "Flushing queue...")
        self.expect_date = 0
        self.expect_text = 0
        self.expect_cash = 0
        # as long as all queues have data, we pop that out and print
        while len(self.dates) > 0 and len(self.texts_complete) > 0 and len(self.money) > 0:
            self.queue_pop()
        while len(self.dates) > 0 and len(self.texts_incomplete) > 0 and len(self.money) > 0:
            output = str(self.dates.popleft()) + str(self.texts_incomplete.popleft()).replace("- ", "") \
                     + '";"' + str(self.money.popleft()) + '"'
            print(output)
        # analytical printout for debug purposes
        while len(self.dates) > 0:
            self.debug(1, "***Unresolved date: " + str(self.dates.popleft()))
        while len(self.texts_incomplete) > 0:
            self.debug(1, "***Unresolved incomplete text: " + str(self.texts_incomplete.popleft()))
        while len(self.texts_complete) > 0:
            self.debug(1, "***Unresolved complete text: " + str(self.texts_complete.popleft()))
        while len(self.money) > 0:
            self.debug(1, "***Unresolved amount: " + str(self.money.popleft()))
        return

    def ignore_item(self, myStr):
        # Test if myStr indicates the end of meaningful text on this page
        if myStr.find("Rechnungsabschluss") >= 0:
            return True
        else:
            return False

    def page_end(self, myStr):
        # Test if myStr indicates the end of meaningful text on this page
        if myStr.find("Summe Zahlung") >= 0 \
                or self.page_nr.match(myStr) \
                or len(myStr) == 1:
            return True
        else:
            return False

    def parse(self, line):
        self.debug(2, "Parsing: " + line)
        # first we need to check for end-of-interesting-text-on-page indicators
        if self.page_end(line):
            # self.queue_flush()
            self.debug(2, "Deactivating page")
            self.page_active = 0
        elif self.ignore_item(line):
            self.debug(2, "Ignoring: " + line)
            self.debug(2, "Deactivating page")
            self.page_active = 0
        else:
            # now we need to find out which type of line was found
            full = self.full_line.match(line)
            part = self.part_line.match(line)
            amount = self.amount_line.match(line)
            text = self.text_line.match(line)

            if full:
                # we received a complete posting in one line and do not expect further data
                self.debug(2, "FULL: " + line)
                output = '"' + full.group(1) + '";"' + svl(full.group(2)) + '";"' \
                         + svl(full.group(3)) + '";"' + svl(full.group(4)).replace(" ", "") + '"'
                print(output)
                self.debug(2, "Activating page")
                self.page_active = 1
            elif part:
                # we received a partial posting with date and first line of text
                self.debug(2, "PART: " + line)
                self.receive_date(part)
                self.debug(2, "Activating page")
                self.page_active = 1
            elif amount:
                # we received a partial posting with only the amount
                self.debug(2, "AMOUNT: " + line)
                self.receive_cash(amount)
                self.debug(2, "Activating page")
                self.page_active = 1
            elif text:
                # we received a partial posting with only the text
                if self.page_active > 0:
                    self.debug(2, "TEXT: " + line)
                    self.receive_text(text)
            else:
                # we received an empty line (otherwise it would have been identified as text)
                if self.page_active > 0:
                    self.debug(2, "EMPTY: " + line)
                    self.receive_blank()
        # end if/else: this was not an end-of-interesting-text-on-page indicator
        return


# -------------------------------------------
if __name__ == "__main__":
    # ---------------------------------------

    for f in sys.argv[1:]:
        pdf_text = convert_pdf_to_txt(f)
        myPDF = pbParser(pdf_text)
        for line in pdf_text.splitlines():
            myPDF.parse(line)
        myPDF.queue_flush()
        del myPDF
