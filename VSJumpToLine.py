"""
ABOUT THIS TOOL:
================
Converts the output of tools such as GCC and Doxygen into a Visual Studio
readable output format. The output of this tool can be used in the output window
of Visual Studio to jump to the corresponding line in the editor.

LICENSE:
========
MIT License

Copyright (c) 2018 kzachmann

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import sys
import os
import logging
import threading
import getopt
import time
import re
import glob
import enum

class FormatSize:
    """
    Format sizes in a human readable format (Base 10 (1000 bytes)).
    """
    def __init__(self, size):
        self.size = size

    def __str__(self):
        byte = 1                    # B
        kilobyte = byte * 1000      # kB 1000 Byte
        megabyte = kilobyte * 1000  # MB 1 000 000 Byte
        gigabyte = megabyte * 1000  # GB 1 000 000 000 Byte
        if self.size >= gigabyte:
            self.size = self.size / gigabyte
            return "{:.2f}GB".format(self.size)
        elif self.size >= megabyte:
            self.size = self.size / megabyte
            return "{:.2f}MB".format(self.size)
        elif self.size >= kilobyte:
            self.size = self.size / kilobyte
            return "{:.2f}kB".format(self.size)
        else:
            return "{}B".format(self.size)

    def __bool__(self):
        if self.size > 0:
            return True
        else:
            return False

class PleaseWait(threading.Thread):
    """
    Simple implementation of a progress bar to indicate to the user that the progress continues.
    """
    # An event that tells the thread to stop
    stopper = threading.Event()
    dot = 0
    def __init__(self):
        super().__init__()

    def run(self):
        time.sleep(0.2)
        while not self.stopper.is_set():
            self.dot = 1
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(0.5)

    def please_wait_on(self):
        """
        Turn progress on
        """
        self.daemon = True
        self.start()

    def please_wait_off(self):
        """
        Turn progress off
        """
        self.stopper.set()
        if self.dot:
            sys.stdout.write("\n")
        sys.stdout.flush()

class Severity(enum.IntEnum):
    """
    Severities enumeration
    """
    ignore = 0
    offset_before = 1
    offset_behind = 2

    note = 10
    info = 20
    warning = 30
    error = 40


class VSJumpToLine:
    """
    The core functionality of VSJumpToLine
    """
    app_name = "VSJumpToLine"   # application name, visual studio jump to line
    app_name_short = "jtol"     # application short name
    app_version = "v1.0.3"      # application version (major.minor.patch)
    header_len = 100

    def __init__(self, args):
        self.exit_success = 0
        self.exit_fail_option = 1
        self.exit_fail_not_exist = 2
        self.exit_fail_decode = 3

        self.cnt_suppressed_infos = 0
        self.cnt_suppressed_notes = 0
        self.cnt_suppressed_warnings = 0
        self.cnt_suppressed_errors = 0

        self.cnt_infos = 0
        self.cnt_notes = 0
        self.cnt_warnings = 0
        self.cnt_errors = 0
        self.cnt_lines = 0

        self.option_file_input = ""
        self.option_line_prefix = ""
        self.option_multi_line = 0
        self.option_suppress_identical = 0
        self.option_working_dir = ""
        self.option_compact = 0
        self.option_quiet = 0

        self.time_start = time.time()
        self.time_end = time.time()

        self.result_list = []

        self.__process_cmdline(args)
        self.__process_input_file()

    def _print_normal(self, string):
        """
        Small helper for normal output.
        """
        print("{}: {}".format(self.app_name_short, string))
        sys.stdout.flush()

    def _print_error(self, string):
        """
        Small helper for error output.
        """
        print("")
        print("{}: ERROR: {}\n".format(self.app_name_short, string))
        sys.stdout.flush()

    def _format_paths(self, path):
        """
        Remove '/' '\' at the beginning and/or at the end.
        """
        if path:
            if (path[0] == '/' or path[0] == '\\'):
                path = path[1:]
            if (path[-1] == '/' or path[-1] == '\\'):
                path = path[:-1]
        return path

    def __match_severity(self, line):
        """
        Determine the severity of a particular line.
        """
        severity = Severity.ignore
        if   ((line.lower().find('note:') > -1) or     # GCC, Doxygen
              (line.lower().find('note[') > -1)):      # IAR
            severity = Severity.note
        elif ((line.lower().find('warning:') > -1) or  # GCC, Doxygen, cmocka
              (line.lower().find('warning[') > -1) or  # IAR, BullseyeCoverage
              (line.lower().find(':fail:') > -1)):     # Unity test framework
            severity = Severity.warning
        elif ((line.lower().find('error:') > -1) or    # GCC, Doxygen, cmocka
              (line.lower().find('error[') > -1) or    # IAR
              (line.lower().find('undefined reference') > -1)): # GCC
            severity = Severity.error
        return severity

    def __match_line_and_column(self, line):
        """
        Try to match only line number and/or column.

        GCC/doxygen/cmocka
        'src/test/testfile.c:124:43: warning: unused parameter 'state' [-Wunused-parameter]'
        'src/test/testfile.c:124: warning: unused parameter 'state' [-Wunused-parameter]'
        '[   LINE   ] --- testcases.c:9: error: Failure!'

        BullseyeCoverage
        '"c:/testfile.c",276  Warning[Pe177]: ...'

        IAR Embedded Workbench
        'c:\test\testfile.h(43) : Warning[Pe1105]: ...'
        """

        # (GCC/doxygen/cmocka | BullseyeCoverage | IAR)
        regex = r":(\d+):((\d+):)?|(\"(.+)\",(\d+))|(\((\d+)\) :)"
        res = re.search(regex, line)
        logging.debug("{}".format(res))
        if res:
            # ':124:43:'
            if res.group(1) and res.group(2):
                logging.debug("{}".format(res.group(1)))
                logging.debug("{}".format(res.group(2)))
                logging.debug("{}".format(res.group(3)))
                line = re.sub(regex, r"(\1,\3):", line)
            # ':124:'
            elif res.group(1):
                logging.debug("{}".format(res.group(1)))
                line = re.sub(regex, r"(\1):", line)
            # '"c:/test.c",276'
            elif res.group(4):
                logging.debug("{}".format(res.group(4)))
                line = re.sub(regex, r"\5(\6):", line)
            # 'c:\test\testfile.h(43) : Warning[Pe1105]: ...'
            elif res.group(7):
                logging.debug("{}".format(res.group(7)))
                line = re.sub(regex, r"(\8):", line)

            logging.info("{}".format(line))
            return line
        else:
            return ""

    def __match_special(self, line):
        """
        Try to match special format assume that line number has been already matched by
        the function 'self.__match_line_and_column()'.

        1. cmocka (unit testing framework for C) output
        '[   LINE   ] --- testcases.c(9): error: Failure!'
        """
        regex = r"^\[   LINE   \] --- (.+)"
        res = re.search(regex, line)
        logging.debug("{}".format(res))
        if res:
            logging.debug("{}".format(res.group(1)))
            line = re.sub(regex, r"\1", line)
            logging.info("{}".format(line))
            return line
        else:
            return ""

    def __convert_to_absolute_path(self, line):
        """
        If only the filename is displayed try using the working directory option to find the absolute path.
        Assume that line number is already in visual studio format.
        """
        if not self.option_working_dir:
            return ""

        regex = r"((^.+)\.(.+))(\(.+\)):"
        res = re.search(regex, line)
        logging.debug("line: {} res:{}".format(line, res))
        if res:
            group1_str = res.group(1)
            # If containing any '/' or '\' assuming that is already an absolute or relative path
            if (group1_str.find('/') > -1) or (group1_str.find('\\') > -1):
                return ""

            logging.debug("group1: {}".format(res.group(1)))
            logging.debug("group2: {}".format(res.group(2)))
            logging.debug("group3: {}".format(res.group(3)))
            logging.debug("group4: {}".format(res.group(4)))

            path = self.option_working_dir + "/**/" + res.group(1)
            for filename_path in glob.iglob(path, recursive=True):
                logging.debug(filename_path)
                line = re.sub(regex, "", line)
                line = filename_path + res.group(4) + ":" + line
                logging.info("{}".format(line))
                return line
            logging.info("File: <{}> not found in working directory!".format(res.group(1)))
            return ""
        else:
            return ""

    def __append_result_list(self, severity, line_processed, line_before):
        """
        Add entry to result list.
        If the option is used to suppress the same messages, only the first message is added to the list.
        """
        abs_path_line = self.__convert_to_absolute_path(line_processed)
        if abs_path_line:
            line_processed = abs_path_line

        # Check if already in list
        already_in_list = False
        if self.option_suppress_identical:
            for entry in self.result_list:
                if line_processed == entry[1]:
                    if   severity == Severity.info:
                        self.cnt_suppressed_infos += 1
                    elif severity == Severity.note:
                        self.cnt_suppressed_notes += 1
                    elif severity == Severity.warning:
                        self.cnt_suppressed_warnings += 1
                    elif severity == Severity.error:
                        self.cnt_suppressed_errors += 1
                    already_in_list = True
                    break

        if not already_in_list:
            if   severity == Severity.info:
                self.cnt_infos += 1
            elif severity == Severity.note:
                self.cnt_notes += 1
            elif severity == Severity.warning:
                self.cnt_warnings += 1
            elif severity == Severity.error:
                self.cnt_errors += 1

            # For multi line option (look one line before)
            if self.option_multi_line and line_before:
                logging.debug("line_look_before: {}".format(line_before))
                self.result_list.append([ severity + Severity.offset_before, line_before])

            self.result_list.append([severity, line_processed])

            return severity
        else:
            return Severity.ignore

    def __process_input_file(self):
        """
        Process the input file.
        """
        try:
            with open(self.option_file_input, "r") as file_tool_output:
                pw = PleaseWait()
                pw.please_wait_on()

                severity = Severity.ignore
                line_before = None
                for file_line in file_tool_output:
                    self.cnt_lines += 1
                    file_line = file_line.replace('\n', '')
                    file_line = file_line.replace('\r', '')

                    severity_last = severity
                    severity = self.__match_severity(file_line)

                    # Match line before, currently only implemented for GCC
                    if (re.search(r": In function.+:", file_line, re.IGNORECASE)):
                        line_before = file_line
                    else:
                        line_before = ""

                    # For multi line option (look behind)
                    if self.option_multi_line and severity_last > Severity.ignore and severity == Severity.ignore:
                        if file_line and file_line[0] == " ":
                            # Check if line contains only spaces
                            if not file_line.isspace():
                                severity = severity_last
                                self.result_list.append([severity_last + Severity.offset_behind, file_line])
                                continue

                    if severity > Severity.ignore:
                        # Line number and/or column should always match
                        line_processed_line_column = self.__match_line_and_column(file_line)
                        # Go into depth
                        if line_processed_line_column:
                            line_processed_special = self.__match_special(line_processed_line_column)
                            if line_processed_special:
                                severity = self.__append_result_list(severity, line_processed_special, line_before)
                                continue
                            else:
                                severity = self.__append_result_list(severity, line_processed_line_column, line_before)
                        else:
                            # Already in Visual Studio format or something new that is not yet covered
                            logging.info("no match for line: {}".format(file_line))
                            self.__append_result_list(severity, file_line, line_before)
                pw.please_wait_off()
        except UnicodeDecodeError as err:
            self._print_error("filename: <{}>, err: {}".format(self.option_file_input, err))
            pw.please_wait_off()
            sys.exit(self.exit_fail_decode)

    def __print_lines(self, severity, result_list):
        """
        Print output lines for a specific severity level.
        """
        first_message = True
        line_before_printed = False
        for entry in result_list:
            if severity == entry[0]:
                if first_message or self.option_compact or line_before_printed:
                    print("{}{}".format(self.option_line_prefix, entry[1]))
                else:
                    print("\n{}{}".format(self.option_line_prefix, entry[1]))
                sys.stdout.flush()
                first_message = False
                line_before_printed = False
            elif (self.option_multi_line == 1 or self.option_multi_line == 3) and (severity + Severity.offset_before == entry[0]): # line before
                # without prefix
                if first_message or self.option_compact:
                    print("{}".format(entry[1]))
                else:
                    print("\n{}".format(entry[1]))
                sys.stdout.flush()
                first_message = False
                line_before_printed = True
            elif (self.option_multi_line == 2 or self.option_multi_line == 3) and (severity + Severity.offset_behind == entry[0]): # line behind
                # without prefix
                print("{}".format(entry[1]))
                sys.stdout.flush()

    def usage(self):
        """
        Print usage if an unknown argument was used or '-h' was entered.
        """
        header_line = ""
        header_line = header_line.center(self.header_len, '-')
        header_title = " " + self.app_name + " " + self.app_version + " - Help "
        header_title = header_title.center(self.header_len, '-')

        self._print_normal(header_line)
        self._print_normal(header_title)
        self._print_normal(header_line)
        self._print_normal("Converts the output of tools such as GCC and Doxygen into a Visual Studio readable output format.")
        self._print_normal("The output of this tool can be used in the output window of Visual Studio to jump to the")
        self._print_normal("corresponding line in the editor.")
        self._print_normal("")
        self._print_normal("Usage: "+ self.app_name + ".py -f filename [-d directory] [-p prefix] [-m {0|1|3}] [-s] [-c]")
        self._print_normal("")
        self._print_normal("-f --file <filename>  : File which contains the tool output")
        self._print_normal("-d --dir <directory>  : Working directory for absolute path search (can be slow)")
        self._print_normal("-p --prefix <prefix>  : Add prefix to output line")
        self._print_normal("-m --multi {1|2|3}    : Enable multi line support")
        self._print_normal("                      : 1 - one line before")
        self._print_normal("                      : 2 - multiple lines behind")
        self._print_normal("                      : 3 - before and behind")
        self._print_normal("-s --suppress         : Suppress identical messages")
        self._print_normal("-c --compact          : Don't add newline between messages")
        self._print_normal("-q --quiet            : Don't show information about the specified options")
        self._print_normal("")
        self._print_normal("Example: " + self.app_name + ".py -f c:/pro/gcc_output.txt -d c:/pro/src -p src/pro/ --multi 2 -s")
        self._print_normal(header_line)

    def __process_cmdline(self, argv):
        """
        Process command-line arguments and output some configuration information.
        Start the entire process.
        """
        try:
            opts, _args = getopt.getopt(argv[1:], "h?scqm:f:p:d:", ["help", "quiet", "multi=", "suppress", "compact", "file=", "prefix=", "dir="])
        except getopt.GetoptError as err:
            self._print_error(err)
            self.usage()
            sys.exit(self.exit_fail_option)
        for opt, arg in opts:
            if opt in ("-h", "-?", "--help"):
                self.usage()
                sys.exit(self.exit_success)
            elif opt in ("-f", "--file"):
                self.option_file_input = arg
                logging.debug("--file: {}".format(self.option_file_input))
            elif opt in ("-p", "--prefix"):
                self.option_line_prefix = arg
                logging.debug("--prefix: {}".format(self.option_line_prefix))
            elif opt in ("-m", "--multi"):
                if arg.isdigit() and int(arg) >= 1 and int(arg) <= 3:
                    self.option_multi_line = int(arg)
                else:
                    self._print_error("argument --multi allows only '1','2' or '3'")
                    self.usage()
                    sys.exit(self.exit_fail_option)
                    break
            elif opt in ("-s", "--suppress"):
                self.option_suppress_identical = 1
            elif opt in ("-c", "--compact"):
                self.option_compact = 1
            elif opt in ("-q", "--quiet"):
                self.option_quiet = 1
            elif opt in ("-d", "--dir"):
                self.option_working_dir = arg
                logging.debug("--dir: {}".format(self.option_working_dir))

        if not self.option_file_input:
            self._print_error("No input file specified!")
            self.usage()
            sys.exit(self.exit_fail_option)

        self.option_file_input = self._format_paths(self.option_file_input)

        if not os.path.isfile(self.option_file_input):
            self._print_error("--filename: <{}>, file does not exits!".format(self.option_file_input))
            sys.exit(self.exit_fail_not_exist)
        else:
            statbuf = os.stat(self.option_file_input)

        if self.option_working_dir:
            self.option_working_dir = self._format_paths(self.option_working_dir)
            if not os.path.isdir(self.option_working_dir):
                self._print_error("--directory: <{}>, directory does not exits!".format(self.option_working_dir))
                sys.exit(self.exit_fail_not_exist)

        header_line = ""
        header_title = " " + self.app_name + " " + self.app_version + " "
        header_title = header_title.center(self.header_len, '-')
        header_line = header_line.center(self.header_len, '-')

        self._print_normal(header_line)
        self._print_normal(header_title)
        self._print_normal(header_line)

        if not self.option_quiet:
            self._print_normal("options:")
            self._print_normal("--filename: <{}>".format(self.option_file_input))
            self._print_normal("--filename: size: <{}>, modified: <{}>".format(FormatSize(os.path.getsize(self.option_file_input)), time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(statbuf.st_mtime))))
            self._print_normal("--directory: <{}>".format(self.option_working_dir))
            self._print_normal("--prefix: <{}>, --multi: <{}>, --suppress: <{}>, --compact: <{}>".format(self.option_line_prefix, self.option_multi_line, self.option_suppress_identical, self.option_compact))
            self._print_normal(header_line)

    def print_output(self):
        """
        Print the whole output (all messages).
        """
        if self.cnt_notes:
            header_title = " notes: {} ".format(self.cnt_notes)
            header_title = header_title.center(self.header_len, '+')
            self._print_normal(header_title)
            self.__print_lines(Severity.note, self.result_list)

        if self.cnt_warnings:
            header_title = " warnings: {} ".format(self.cnt_warnings)
            header_title = header_title.center(self.header_len, '*')
            self._print_normal(header_title)
            self.__print_lines(Severity.warning, self.result_list)

        if self.cnt_errors:
            header_title = " errors: {} ".format(self.cnt_errors)
            header_title = header_title.center(self.header_len, '#')
            self._print_normal(header_title)
            self.__print_lines(Severity.error, self.result_list)

        self.time_end = time.time()

        header_line = ""
        if self.cnt_errors or self.cnt_warnings:
            header_line = header_line.center(self.header_len, '~')
        else:
            header_line = header_line.center(self.header_len, '=')

        self._print_normal(header_line)
        self._print_normal("finished (totals): time: {:.2f}s, errors: {}/{}, warnings: {}/{}, notes: {}/{}, lines: {}".format(
            self.time_end - self.time_start,
            self.cnt_errors + self.cnt_suppressed_errors, self.cnt_suppressed_errors,
            self.cnt_warnings + self.cnt_suppressed_warnings, self.cnt_suppressed_warnings,
            self.cnt_notes + self.cnt_suppressed_notes, self.cnt_suppressed_notes,
            self.cnt_lines))
        self._print_normal(header_line)

def main(args):
    logging.getLogger().setLevel(logging.WARN)
    #logging.basicConfig(format='[%(asctime)s] [%(levelname)7s] [%(funcName)-20.20s] [%(lineno)03d] - %(message)s')
    logging.basicConfig(format='[%(levelname)7s] [%(funcName)-10.10s] [%(lineno)03d] - %(message)s')

    jtol = VSJumpToLine(args)
    jtol.print_output()

    sys.exit(jtol.exit_success)

if __name__ == "__main__":
    main(sys.argv)
