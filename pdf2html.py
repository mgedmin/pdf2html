#!/usr/bin/python
"""
Converts PDF to HTML e-books.

Relies on pdftohtml (http://pdftohtml.sourceforge.net/).  Requires Python 2.5
or later.

Method of operation:

    1. Run pdftohtml -xml on the PDF file
    2. Process the XML file, detect paragraph boundaries by paying careful
       attention to first-line indents
    3. Produce an HTML

The HTML produced differs from the one you'd get from pdftohtml in these ways:

    * Paragraphs are preserved; line breaks inside paragraphs are lost.
    * Multiple adjacent spaces are left as spaces, not converted to a run of
      &nbsp;
    * Page boundaries are discarded, not rendered as <hr>
    * The HTML produced is modern XHTML, not ancient HTML 3 with an explicit
      dark-grey bgcolor on the <BODY>.

Bugs:

    * doesn't handle superscript well
    * doesn't handle small caps
    * loses information such as fonts and colours

Config file:

    Put a .pdf2htmlrc in the same directory as the source PDF file.  Every
    section, denoted [pattern] can apply options to files matching the
    pattern, e.g.

       [hello.pdf]
       header_pos = 166

       [*.pdf]
       footer_pos = -1

    Currently the only options you can specify this way are header and
    footer positions if you want to suppres header/footer text from
    the output.  The position is specified in points, with 0 at the top
    of the page, increasing downwards.

Copyright (c) 2009-2010 Marius Gedminas <marius@gedmin.as>.
Licenced under the GNU GPL.
"""

import optparse
import os
import shutil
import subprocess
import sys
import tempfile
import ConfigParser
import fnmatch
import re
from collections import defaultdict
from xml.etree import cElementTree as ET


__version__ = '0.4'
__author__ = 'Marius Gedminas'


class Error(Exception):
    pass


class Options(object):
    """Conversion options"""

    _defs = [
        ('debug', bool),
        ('keep', bool),
        ('title', str),
        ('subtitle', str),
        ('header_pos', int),
        ('footer_pos', int),
        ('skip_initial_pages', int),
        ('skip_generator', bool),
    ]

    _help = dict(
        debug='print verbose diagnostics',
        keep='keep temporary files',
        header_pos='suppress text above this point (header)',
        footer_pos='suppress text below this point (footer)',
        title='document title',
        subtitle='document subtitle',
        skip_initial_pages='skip the first N pages of output',
        skip_generator='skip <meta name="generator" ...>',
    )

    def __init__(self):
        for name, type in self._defs:
            setattr(self, name, None)

    def add_to_option_parser(self, parser):
        for name, type in self._defs:
            optname = name.replace('_', '-')
            if type is bool:
                parser.add_option('--' + optname, action='store_true',
                                  help=self._help[name])
                parser.add_option('--no-' + optname, action='store_false',
                                  dest=name, help=optparse.SUPPRESS_HELP)
            else:
                parser.add_option('--' + optname, type=type,
                                  help=self._help[name])

    def update_from_config_section(self, cp, section):
        getters = {bool: cp.getboolean,
                   int: cp.getint,
                   str: cp.get}
        for name, type in self._defs:
            if cp.has_option(section, name):
                value = getters[type](section, name)
                setattr(self, name, value)

    def update_from_optparse(self, opts):
        for name, type in self._defs:
            value = getattr(opts, name, None)
            if value is not None:
                setattr(self, name, value)


def parse_config_file(options, config_file, filename_to_match='*'):
    cp = ConfigParser.SafeConfigParser()
    cp.read([config_file])
    for s in cp.sections():
        if fnmatch.fnmatch(filename_to_match, s):
            if options.debug:
                print "Applying [%s] from %s" % (s, config_file)
            options.update_from_config_section(cp, s)


def convert_pdf_to_html(pdf_file, html_file, opts=None):
    tmpdir = tempfile.mkdtemp('pdf2html')
    try:
        xml_file = os.path.join(tmpdir, 'data') # pdf2html always adds .xml
        subprocess.check_call(['pdftohtml', '-xml', pdf_file, xml_file])
        xml_file += '.xml'
        convert_pdfxml_to_html(xml_file, html_file, opts)
    finally:
        if opts and opts.keep:
            print "Temporary files kept in %s" % tmpdir
        else:
            shutil.rmtree(tmpdir)


def convert_pdfxml_to_html(xml_file, html_file, opts=None):
    debug = False
    if opts:
        debug = opts.debug

    # The structure of the pdf2xml documents is this:
    #   <pdf2xml>
    #     <page number="1" position="absolute" top="0" left="0"
    #           height="800" width="600" >
    #       <fontspec id="0" size="12" family="Times" color="#000000" />
    #       ...
    #       <text top="100" left="60" width="200" height="13"
    #             font="0"><i><b>Some text</b></i></text>
    #       ...
    #     </page>
    #     ...
    #   </pdf2xml>
    # Notes:
    #   * The scope of <fontspecs> is larger than a single page
    #   * Coordinates are typical screen coordinates: i.e. (0, 0) is top-left
    #     and y increases downwards
    tree = ET.parse(xml_file)
    root_tag = tree.getroot().tag
    if root_tag != 'pdf2xml':
        raise Error('Expected a pdf2xml document, got %s' % root_tag)

    html = ET.Element('html')
    html.text = html.tail = '\n'
    head = ET.SubElement(html, 'head')
    head.text = head.tail = '\n'
    charset = ET.SubElement(head, 'meta',
                            {'http-equiv': 'content-type',
                             'content': 'text/html; charset=UTF-8'})
    charset.tail = '\n'
    if opts and not opts.skip_generator:
        generator = ET.SubElement(head, 'meta',
                                  name='generator',
                                  content='pdf2html %s by %s' % (__version__,
                                                                 __author__))
        generator.tail = '\n'
    title = ET.SubElement(head, 'title')
    if opts and opts.title:
        title.text = opts.title
    else:
        title.text = os.path.basename(html_file)
    title.tail = '\n'
    body = ET.SubElement(html, 'body')
    body.text = body.tail = '\n'
    if opts.title:
        h1 = ET.SubElement(body, 'h1')
        h1.text = opts.title
        h1.tail = '\n'
    if opts.subtitle:
        h2 = ET.SubElement(body, 'h2')
        h2.text = opts.subtitle
        h2.tail = '\n'

    class Font(object):
        def __init__(self, size, family, color):
            self.size = size
            self.family = family
            self.color = color

        def __hash__(self):
            return hash(self.size, self.family, self.color)

        def __eq__(self, other):
            return type(other) == type(self) and (self.size, self.family,
                                                  self.color) == (other.size,
                                                  other.family, other.color)

        def __ne__(self, other):
            return not self.__eq__(other)

    fonts = {}
    for page in tree.findall('page'):
        for fontspec in page.findall('fontspec'):
            font = Font(fontspec.get('size'), fontspec.get('family'),
                        fontspec.get('color'))
            fonts[fontspec.get('id')] = font

    def iter_attrs(attr, pagefilter=None):
        frequencies = defaultdict(int)
        for page in tree.findall('page'):
            if pagefilter and not pagefilter(page):
                continue
            for chunk in page.findall('text'):
                yield chunk.get(attr)

    def count_frequencies(attr, pagefilter=None):
        frequencies = defaultdict(int)
        for value in iter_attrs(attr, pagefilter):
            frequencies[value] += 1
        return frequencies

    def n_most_frequent(attr, n, pagefilter=None, extratitle=''):
        frequencies = count_frequencies(attr, pagefilter)
        frequencies = [(freq, value) for value, freq in frequencies.items()]
        frequencies.sort()
        if debug:
            if not extratitle and pagefilter and pagefilter.__doc__:
                extratitle = " (%s)" % pagefilter.__doc__.strip()
            print "Top 5 most frequent values of %r:%s" % (attr, extratitle)
            for f, v in frequencies[-5:]:
                bar = '*' * (30 * f / frequencies[-1][0])
                print '  %6d chunks have value %-6s %s' % (f, v, bar)
        return [value for (freq, value) in frequencies[-n:]]

    def most_frequent(attr):
        values = n_most_frequent(attr, 1)
        if values:
            return values[0]
        else:
            return object() # something not equal to anything else

    def margin_and_indent(pagefilter=None):
        xs = sorted(map(int, n_most_frequent('left', 2, pagefilter)))
        if len(xs) == 2:
            return xs
        elif len(xs) == 1:
            # object() is something not equal to anything else
            return xs[0], object()
        else:
            # object() is something not equal to anything else
            return object(), object()

    def odd_pages(page):
        "odd pages"
        return int(page.get('number')) % 2 == 1

    def even_pages(page):
        "even pages"
        return int(page.get('number')) % 2 == 0

    most_frequent_height = most_frequent('height')
    most_frequent_font = fonts[most_frequent('font')]
        # XXX sometimes you have more than one fontspec with the same
        # attributes (family, size, color), this might skew the frequency
        # distribution somewhat

    # XXX could crash if there are no text chunks or all of them are at the
    # same x position
    odd_left, odd_indent = margin_and_indent(odd_pages)
    even_left, even_indent = margin_and_indent(even_pages)

    horiz_leeway = abs(even_left - odd_left)
    indents = set((odd_indent, even_indent))

    # XXX: could crash if there are no text chunks at all
    if debug:
        max_text_width = max(int(w) for w in iter_attrs('width'))
        print "Widest text chunk = %d" % max_text_width
    text_width = max(map(int, n_most_frequent('width', 3)))
    if debug:
        print "Guessing paragraph width = %d" % text_width
    text_width = text_width * 8 / 10

    if debug:
        print "Guessing left margin = %d (odd pages), %d (even pages)" % (odd_left, even_left)
        print "Guessing indent = %d (odd pages), %d (even pages)" % (odd_indent, even_indent)
        print "Guessing horizontal leeway = %d" % (horiz_leeway)
        print "Guessing minimum paragraph line width = %d" % text_width

    header_pos = None
    if opts and opts.header_pos and opts.header_pos != -1:
        header_pos = opts.header_pos
        if opts.debug:
            print "Suppressing header text above %d" % header_pos
    footer_pos = None
    if opts and opts.footer_pos and opts.header_pos != -1:
        footer_pos = opts.footer_pos
        if opts.debug:
            print "Suppressing footer text below %d" % footer_pos

    def looks_like_a_heading(chunk):
        if len(chunk) != 1:
            bold = None
        else:
            bold = chunk
            while bold.tag != 'b':
                if len(bold) != 1:
                    bold = None
                    break
                bold = bold[0]
        if bold:
            return (fonts[chunk.get('font')] != most_frequent_font
                    and int(chunk.get('height')) >= int(most_frequent_height)
                    and bold.text
                    and any(c.isalpha() for c in bold.text))
        else:
            return (fonts[chunk.get('font')] != most_frequent_font
                    and int(chunk.get('height')) > int(most_frequent_height)
                    and chunk.text
                    and all(c.isdigit() for c in chunk.text))

    def drop_cap(prev_chunk, chunk):
        if not prev_chunk.text or not chunk.text:
            return False
        if not 1 <= len(prev_chunk.text) <= 2:
            return False
        if int(prev_chunk.get('height')) <= int(chunk.get('height')):
            return False
        drop_cap_horiz_gap = int(prev_chunk.get('width')) / 2
        drop_cap_vert_gap = int(prev_chunk.get('height')) / 4
        if abs(int(prev_chunk.get('left')) + int(prev_chunk.get('width')) - int(chunk.get('left'))) > drop_cap_horiz_gap:
            return False
        return (abs(int(prev_chunk.get('top')) - int(chunk.get('top'))) > drop_cap_vert_gap or
                abs(int(prev_chunk.get('top')) + int(prev_chunk.get('height'))
                    - int(chunk.get('top')) - int(chunk.get('height'))) > drop_cap_vert_gap)


    para = None
    prev_chunk = None
    for page in tree.findall('page'):
        if odd_pages(page):
            indent = odd_indent
        else:
            indent = even_indent
        for chunk in sorted(page.findall('text'),
                            key=lambda chunk: (int(chunk.get('top')),
                                               int(chunk.get('left')))):
            suppress = False
            if opts and opts.skip_initial_pages and int(page.get('number')) <= opts.skip_initial_pages:
                suppress = True
                suppress_reason = 'INITIAL PAGES'
            elif header_pos and int(chunk.get('top')) <= header_pos:
                suppress = True
                suppress_reason = 'HEADER'
            elif footer_pos and int(chunk.get('top')) >= footer_pos:
                suppress = True
                suppress_reason = 'FOOTER'
            if prev_chunk is None or suppress:
                continues_paragraph = False
            else:
                sanity_limit = (int(prev_chunk.get('top'))
                                + int(prev_chunk.get('height'))
                                + int(fonts[prev_chunk.get('font')].size) / 2)
                continues_paragraph = (
                    int(chunk.get('left')) != indent and
                    int(chunk.get('left')) <= int(prev_chunk.get('left')) + horiz_leeway and
                    int(prev_chunk.get('width')) >= text_width and
                    int(chunk.get('top')) <= sanity_limit and
                    fonts[chunk.get('font')] == fonts[prev_chunk.get('font')]
                ) or (
                    chunk.get('top') == prev_chunk.get('top')
                ) or drop_cap(prev_chunk, chunk)
                if debug and chunk.get('assert_continues') and not continues_paragraph:
                    print "*** DEBUG assertion failed"
                    print ' ', ET.tostring(prev_chunk).rstrip()
                    print ' ', ET.tostring(chunk).rstrip()
                    print "tops match?", chunk.get('top') == prev_chunk.get('top')
                    print "OR drop cap:", drop_cap(prev_chunk, chunk)
                    print "OR not indent:", int(chunk.get('left')) != indent
                    print "AND same or to the left:", int(chunk.get('left')) <= int(prev_chunk.get('left')) + horiz_leeway
                    print "AND prev chunk wide enough:", int(prev_chunk.get('width')) >= text_width
                    print "AND same font:", fonts[chunk.get('font')] == fonts[prev_chunk.get('font')]
                    print "AND close enough vertically:", int(chunk.get('top')) <= sanity_limit
                    print "where sanity_limit = %d + %d + %d = %d" % (
                            int(prev_chunk.get('top')),
                            int(prev_chunk.get('height')),
                            int(fonts[prev_chunk.get('font')].size) / 2,
                            sanity_limit)

            if para is not None and continues_paragraph:
                # join with previous
                if chunk.text is None:
                    chunk.text = ''
                if drop_cap(prev_chunk, chunk):
                    joiner = ''
                else:
                    joiner = '\n'
                if len(para):
                    if para[-1].tail:
                        para[-1].tail += joiner + chunk.text
                    else:
                        para[-1].tail = joiner + chunk.text
                else:
                    if para.text:
                        para.text += joiner + chunk.text
                    else:
                        para.text = chunk.text
                para[len(para):] = chunk[:]
            else:
                # start new paragraph
                if looks_like_a_heading(chunk):
                    new_para = ET.Element('h2')
                else:
                    new_para = ET.Element('p')
                new_para.text = chunk.text
                new_para[:] = chunk[:]
                new_para.tail = '\n'
                if suppress:
                    # I hate ElementTree: it escapes < and > inside comments.
                    # This should be fixed in Python 2.7:
                    # http://bugs.python.org/issue2746
                    comment = ET.Comment('%s: %s' % (suppress_reason, ET.tostring(new_para).strip()))
                    comment.tail = '\n'
                    body.append(comment)
                else:
                    para = new_para
                    body.append(para)
            if not suppress:
                prev_chunk = chunk

    def postprocess(s):
        s = re.sub(r'-\n([a-z])', r'\1', s)
        s = s.replace(u'\uFB00', 'ff')
        s = s.replace(u'\uFB01', 'fi')
        s = s.replace(u'\uFB02', 'fl')
        s = s.replace(u'\uFB03', 'ffi')
        s = s.replace(u'\uFB04', 'ffl')
        return s

    for item in html.getiterator():
        if item.text:
            item.text = postprocess(item.text)
        if item.tail:
            item.tail = postprocess(item.tail)

    file(html_file, 'w').write(ET.tostring(html))


def main():
    options = Options()
    parser = optparse.OptionParser(usage='%prog input.pdf [output.html]')
    parser.add_option('--version', action='store_true',
                      help='print version and exit')
    options.add_to_option_parser(parser)

    opts, args = parser.parse_args()
    if opts.version:
        print "pdf2html.py v%s by %s" % (__version__, __author__)
        return
    if len(args) < 1:
        parser.error('please specify an input file name')
    if len(args) > 2:
        parser.error('too many arguments')

    pdf_name = args[0]
    if len(args) > 1:
        output_name = args[1]
    else:
        output_name = os.path.splitext(pdf_name)[0] + '.html'

    # special_case, since parse_config_file wants this defined early
    options.debug = opts.debug

    config_name = os.path.join(os.path.dirname(pdf_name), '.pdf2htmlrc')
    parse_config_file(options, config_name, pdf_name)

    # command-line options override those set in the config file
    options.update_from_optparse(opts)

    try:
        if os.path.splitext(pdf_name)[1] == '.xml':
            convert_pdfxml_to_html(pdf_name, output_name, options)
        else:
            convert_pdf_to_html(pdf_name, output_name, options)
    except Error, e:
        sys.exit(str(e))


if __name__ == '__main__':
    main()
