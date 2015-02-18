pdf2html
========

Converts PDF e-books to HTML.  Relies on the PDF actually having text (not images).

It's a wrapper for pdftohtml_ (from poppler-utils) that tries to restore paragraph
structure by looking at text positioning and font information.  It requires Python 2.

The HTML produced differs from the one you'd get from pdftohtml in these ways:

* Paragraphs are preserved; line breaks inside paragraphs are lost.
* Multiple adjacent spaces are left as spaces, not converted to a run of &nbsp;
* Page boundaries are discarded, not rendered as <hr>
* The HTML produced is modern XHTML, not ancient HTML 3 with an explicit dark-grey
  bgcolor on the <BODY> (what's up with that???).

.. _pdftohtml: http://pdftohtml.sourceforge.net/


Usage
-----

Usage: pdf2html input.pdf [output.html]

Options:
  -h, --help            show this help message and exit
  --version             print version and exit
  --debug               print verbose diagnostics
  --keep                keep temporary files
  --title=TITLE         document title
  --subtitle=SUBTITLE   document subtitle
  --header-pos=HEADER_POS
                        suppress text above this point (header)
  --footer-pos=FOOTER_POS
                        suppress text below this point (footer)
  --leading=LEADING     override autodetected intra-paragraph leading
  --indent=INDENT       override autodetected indent
  --left-margin=LEFT_MARGIN
                        override autodetected left margin
  --horiz-leeway=HORIZ_LEEWAY
                        override autodetected horizontal leeway
  --skip-initial-pages=SKIP_INITIAL_PAGES
                        skip the first N pages of output
  --skip-generator      skip <meta name="generator" ...>
  --encoding=ENCODING   character set for the HTML
  

Configuration
-------------

Put a .pdf2htmlrc in the same directory as the source PDF file.  Every
section, denoted [pattern] can apply options to files matching the
pattern, e.g. ::

    [hello.pdf]
    header_pos = 166
    [*.pdf]
    footer_pos = -1
    
All options you can specify on the command line can be specified
in the config file (with the obvious exceptions of --version and --help).

Currently the most useful options you can specify this way are header and
footer positions if you want to suppres header/footer text from the output.
The position is specified in points, with 0 at the top of the page,
increasing downwards.  All text above the header pos as well as all text
below the footer pos is discarded.  Specify -1 (which is the default) to
disable.  To find out the right values, use --keep and take a look at
text coordinates in the intermediate .xml file.


Bugs
----

* it's not easy to use; overriding the heuristics when they go wrong requires a deep knowledge of the internals
* doesn't handle superscript well
* doesn't handle small caps
* loses information such as fonts and colours
* there are no tests
* it doesn't support Python 3
