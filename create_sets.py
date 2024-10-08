#!/usr/bin/env python3

# pylint: disable=too-many-lines

"""
CBDA validation and training set creation.

This script defines validation and training sets for a CBDA project.

Inputs:
    File name of original data file.

        This may be a zip file or a plain text csv file.

        If a zip file is specified, the following assumptions are made:
           There is only one file in the file archive.

           The name of the file in the file archive is the same as the
           name of the zip file, except it has no path and it ends with
           '.csv' instead of '.zip'.

           The contents file in the file archive conform to the same
           format as a file read directly from disk, described next.

        The following assumptions are made about the contents of the actual
        data file, whether read from a zip file or directly from a regular
        file:
            It is a text file.

            It has a header line with column names.

            It is a csv file/

            All lines have the same number of columns, including the header
            line.

    The name of a Python Pickle file containing the following information
    about the original data file:
       The number of lines in the original data file.

       The number of comma separated columns in the header line of the
       original data file. It is assumed that all other lines in the file
       also have that number of columns.

    The number of rows to extract.
        The specific rows to extract are chosen at random from the original
        file. The first row is not included, nor are any rows in the
        validation set.

    The number of columns to extract.
        The specific columns to extract are chosen at random.

    The case number column ordinal.
        To exclude from the selection of data columns for a data set, but to
        be written to each training set in addition to the selected data
        columns.  This is the column whose value corresponds to each patient.

    The output column ordinal.
        To exclude from the selection of data columns for a data set, but to
        be written to each training set in addition to the selected data
        columns.  This is the outcome column whose value is to be predicted
        by the algorithm defined by the machine learning processing of the
        training sets generated here.

    The number of training sets to create.

    The starting set number. Optional.
        If not present the default value is 1.

        Needed to create unique output file names when this script is run
        more than once for an original data file, to create more training and
        validation sets than the max number of open files allowed.

    The file name of a file containing an optional set of columns to restrict
    the selection to. Optional.
        If not present all columns are available to select from, except the
        case number column and output column.

        If present only the specified columns are available to select from.
        These must not include the case number column or output column.

        This is for a second set of training/validation runs to determine
        which subset of the important columns, identified by the first
        training/validation runs, are most useful.


        This file has 2 numbers per line:

            A column ordinal.

            A value indicating the predictive power ranking of that column.
            The columns should appear in descending order by this ranking.
            The column with the highest ranking should appear first, etc.
            However, this is not checked by this script.

Outputs:
   An output file for each training set.


   A validation set file for each training set file.
       A training set file will not contain any of the original data file
       lines as its corresponding validation set file.
"""

import sys
import argparse
import os
import pickle
import random
from contextlib import contextmanager
import zipfile
import time

class SelectionSet:

    """

    A base class for data sets to be selected from an original data file.

    Each subclass should have the following members:

        row_ordinals: A Python set object that has the row ordinals of the rows
                      (lines) of the original file to be written for this set.

        column_ordinals: A list of the randomly selected columns to write from
                         a line of the original file. It does not include the
                         case number column or the output column.

        output_columns: A list of the columns to write from a line of the
                        original file. It is the output_ordinal columns plus
                        the case number and output columns. The case number is
                        the first column, the output column is the second
                        column followed by the column_ordinals. The
                        column_ordinals are sorted in ascending order when
                        appended to output_columns, so they are in the same
                        order as in the original file.

        set_file: An open file object to write the selected data to.

    """

    def __init__(self):
        self.row_ordinals = set()
        self.column_ordinals = None
        self.output_columns = None
        self.set_file = None

    def define_output_columns(self, args):

        """
        For writing the selected columns in the same order as they are in the
        original file. Also, to optionally include the case number and
        output columns in the output, as the first and second columns.

        When creating training sets, both the training set and its associated
        validation set will shave the case number and output as the first two
        columns of the set file. These are optional for generic sets.
        """

        column_ordinals_sorted = list(self.column_ordinals)
        column_ordinals_sorted.sort()

        self.output_columns = []

        # This is included even if it is None. In that case it is to indicate
        # writing the row ordinal instead. This is for generic sets, for which
        # the case number is optional.
        self.output_columns.append(args.case_column)

        if args.outcome_column is not None:
            self.output_columns.append(args.outcome_column)

        self.output_columns += column_ordinals_sorted

    def get_random_ordinals(self, ordinals, count):

        """
        Get a set of count random elements from ordinals.

        ordinals are a list of data line ordinals from the original file.

        count should be an integer.
        """

        ordinal_sample = set(random.sample(ordinals, count))
        return ordinal_sample

    def get_random_ordinals_exclude(self, count, start, end, exclude):

        """
        Get a set of count random integers between start and end, inclusive,
        but not including any integers in the exclude.

        This is without replacement, so a random integer should also not
        already be in the result set. This is enforced by the set data type
        which does not have duplciates. The set add function doesn't change
        the set if it already has the element being added.

        count, start and end should be integers.

        start should be < end

        count should be < (end - start + 1)

        exclude should be a set of integers. It may be empty.

        """
        ordinals = set()
        while len(ordinals) < count:
            r = random.randint(start, end)
            if not r in exclude:
                ordinals.add(r)

        return ordinals

    def write_ordinals(self, ordinals, file_name):

        """
        Write a set of ordinals to a file, in ascending numerical order.

        These are typically needed by subsequent machine learning steps, not part
        of the data set selection process.
        """

        sorted_ordinals = sorted(ordinals)
        with open(file_name, 'w', encoding='utf_8') as ordinal_file:
            for o in sorted_ordinals:
                ordinal_file.write(str(o) + '\n')

    def check_line(self, ordinal, fields):

        """
        Check a line from the original file, to see if fields from it should be
        written for this training set.

        output_columns is sorted in ascending order by column ordinal, so the
        columns will be written in the same order they are in the original
        file, except for the case number column and output column, which if
        present are always the first two columns.
        """

        if ordinal in self.row_ordinals:
            # This line is for this selection set.

            fields_to_write = []
            for i, o in enumerate(self.output_columns):

                if i == 0 and self.output_columns[i] is None:
                    # This is for a generic set that is not including the case
                    # column. Write the row ordinal instead.
                    fields_to_write.append(str(ordinal))
                else:
                    # Write a data column.
                    # Because we count column ordinals from 1, but list indices
                    # start at 0.
                    o1 = o - 1
                    fields_to_write.append(fields[o1])

            # Write the fields to the training set file.
            field_str = ','.join(fields_to_write) + '\n'
            self.set_file.write(field_str)

# pylint: disable=too-many-instance-attributes
class ValidationSet(SelectionSet):

    """
    A class to represent the information for a validation set to be created.

    Each validation set has an output file name, output file object and a set
    of row ordinals for the lines of the original file for this validation set
    and a set of column ordinals for the columns of the original file for this
    validation set.
    """

    # The subset of row ordinals from the original data file to use for
    # sampling when creating a validation set.
    available_ordinals = None

    # pylint: disable=too-many-arguments
    def __init__(self, file_ordinal, original_column_count, args, row_count,
                 column_set, prefix='validation-set-'):

        if ValidationSet.available_ordinals is None:
            msg = 'ValidationSet: available_ordinals has not been defined'
            raise ValueError(msg)

        SelectionSet.__init__(self)

        # Define these file items as None so the cleanup function can be
        # called to cleanup up any open or created files if a file exception
        # occurs part was through the constructor.
        self.row_ordinal_file_name = None
        self.column_ordinal_file_name = None
        self.set_file = None

        # Used for output file names and error mesages.
        # This is the same ordinal as the associated training set.
        self.file_ordinal = file_ordinal

        self.row_ordinals = self.get_random_ordinals(
                                     ValidationSet.available_ordinals,
                                     row_count)

        # Determine the columns to use for this validation set. If a column set
        # was provided, use it. Otherwise use a random set of columns.
        self.column_ordinals = None
        self.output_columns = None
        if column_set is not None:
            self.column_ordinals = column_set
            self.define_output_columns(args)
        else:
            exclude_cols = set([args.case_column, args.outcome_column])
            self.column_ordinals = self.get_random_ordinals_exclude(
                                          args.column_count, 1,
                                          original_column_count, exclude_cols)
            self.define_output_columns(args)

        self.file_name = f'{prefix}{self.file_ordinal}.csv'

        f = f'{prefix}{self.file_ordinal}-row-ordinals'
        self.row_ordinal_file_name = f

        try:
            self.write_ordinals(self.row_ordinals, self.row_ordinal_file_name)
        except OSError as e:
            self.cleanup()
            raise e

        f = f'{prefix}{self.file_ordinal}-column-ordinals'
        self.column_ordinal_file_name = f
        if self.column_ordinals is not None:
            try:
                self.write_ordinals(self.column_ordinals,
                                    self.column_ordinal_file_name)
            except OSError as e:
                self.cleanup()
                raise e

        # pylint: disable=consider-using-with
        try:
            self.set_file = open(self.file_name, 'w', encoding='utf_8')
        except OSError as e:
            self.cleanup()
            raise e

    def cleanup(self):

        """
        Cleanup any files created by this ValidationSet.

        Called when the constructor detects a file error creating one of
        these files or when the owning TrainingSet contruction failed, in
        either case typically due to a file open failure because of too many
        open files.
        """

        if (self.row_ordinal_file_name is not None and
                os.access(self.row_ordinal_file_name, os.R_OK)):
            os.remove(self.row_ordinal_file_name)

        if (self.column_ordinal_file_name is not None and
                os.access(self.column_ordinal_file_name, os.R_OK)):
            os.remove(self.column_ordinal_file_name)

        if self.set_file is not None:
            if not self.set_file.closed:
                self.set_file.close()

            if os.access(self.file_name, os.R_OK):
                os.remove(self.file_name)

    def close(self):
        """
        Close the selection set file.
        To be called once the selection set has been fully processed.
        """
        self.set_file.close()

# pylint: disable=too-many-instance-attributes
class TrainingSet(SelectionSet):

    """
    A class to represent the information for a training set to be created.

    Each training set has an output file name, output file object and a set of
    row ordinals for the lines of the original file for this training set and
    a set of column ordinals for the columns of the original file for this
    training set.

    Each training set has its own validation set. The training set
    will not choose row ordinals that are in any validation set, its own
    validation set or the validation set for another training set,
    since the training set row ordinals are sampled from a distinct subset
    of the original file row ordinals than the validation sets are sampled
    from.

    The training set and and its validation set will both use the same columns
    from the original file.
    """

    # The subset of row ordinals from the original data file to use for
    # sampling when creating a training set.
    available_ordinals = None

    def __init__(self, file_ordinal, original_column_count, args, column_set):

        if TrainingSet.available_ordinals is None:
            msg = 'TrainingSet: available_ordinals has not been defined'
            raise ValueError(msg)

        SelectionSet.__init__(self)

        # Define these file items as None so the cleanup function can be
        # called to cleanup up any open or created files if a file exception
        # occurs part was through the constructor.
        self.row_ordinal_file_name = None
        self.set_file = None

        # Used for output file names and error mesages.
        self.file_ordinal = file_ordinal

        self.validation_set = ValidationSet(self.file_ordinal,
                                            original_column_count, args,
                                            args.validation_row_count,
                                            column_set)

        # The training set uses the same columns as the validation set.
        self.column_ordinals = self.validation_set.column_ordinals

        self.row_ordinals = self.get_random_ordinals(
                                     TrainingSet.available_ordinals,
                                     args.training_row_count)

        self.define_output_columns(args)

        self.file_name = f'training-set-{file_ordinal}.csv'

        f = f'training-set-{file_ordinal}-row-ordinals'
        self.row_ordinal_file_name = f

        try:
            self.write_ordinals(self.row_ordinals, self.row_ordinal_file_name)
        except OSError as e:
            self.cleanup()
            raise e

        # pylint: disable=consider-using-with
        try:
            self.set_file = open(self.file_name, 'w', encoding='utf_8')
        except OSError as e:
            self.cleanup()
            raise e

    def cleanup(self):

        """
        Cleanup any files created by this TrainingSet, including any by its
        associated ValidationSet.

        Called when the TrainingSet contruction failed, typically due to
        a file open failure because of too many open files.
        """

        if (self.row_ordinal_file_name is not None and
                os.access(self.row_ordinal_file_name, os.R_OK)):
            os.remove(self.row_ordinal_file_name)

        if self.set_file is not None:
            if not self.set_file.closed:
                self.set_file.close()

            if os.access(self.file_name, os.R_OK):
                os.remove(self.file_name)

        self.validation_set.cleanup()

    def check_line(self, ordinal, fields):

        """
        If doing a validation set for each training set, then check this
        training set's validation set if it should write the line.

        In either case check this training set if it should write the line.
        """

        if self.validation_set is not None:
            self.validation_set.check_line(ordinal, fields)

        super().check_line(ordinal, fields)

    def close(self):
        """
        Close the selection set file, for this TraininSet and its
        ValidaitonSet.

        To be called once the selection set has been fully processed.
        """
        self.set_file.close()
        self.validation_set.close()

def define_and_get_args(args=None):

    """
    Define and get the command line options.
    """

    parser = argparse.ArgumentParser()

    msg = 'The file name of the original data set'
    parser.add_argument('-i', '--original-file', dest='original_file_name',
                        help=msg, type=str, default=None, required=True)

    msg = 'The file name of the Pickle file with the original data file'
    msg += ' information.'
    parser.add_argument('--odfi', '--original-data-file-info',
                        dest='original_data_file_info', help=msg, type=str,
                        default=None, required=True)

    msg = 'The number of sets to create, training or generic'
    parser.add_argument('--sc', '--set-count', dest='set_count', help=msg,
                        type=int, required=True)

    msg = 'The number of rows to extract for each generic set.'
    parser.add_argument('--grc', '--generic-row-count',
                        dest='generic_row_count', help=msg,
                        type=int, required=False)

    msg = 'The percentage of original file records to use'
    msg += ' for sampling training sets. The remaining record to use for'
    msg += ' sampling validation sets.'
    parser.add_argument('--tp', '--training-percent', dest='training_percent',
                        help=msg, type=float, required=False)

    msg = 'The number of rows to extract for each training set.'
    parser.add_argument('--trc', '--training-row-count',
                        dest='training_row_count', help=msg, type=int,
                        required=False)

    msg = 'The number of rows to extract for each validation set.'
    parser.add_argument('--vrc', '--validation-row-count',
                        dest='validation_row_count', help=msg, type=int,
                        required=False)

    msg = 'The file name of a file with a resticted set of column ordinals'
    msg += ' to use'
    parser.add_argument('--cs', '--column-set', dest='column_set_file_name',
                        help=msg, type=str, required=False)

    msg = 'The starting number of columns to use from the column set file.'
    parser.add_argument('--css', '--column-set-start', dest='column_set_start',
                        help=msg, type=int, required=False)

    msg = 'The number of columns to extract for each validation'
    msg += ' and training set or for each generic set.'
    parser.add_argument('--cc', '--column-count', dest='column_count',
                        help=msg, type=int, required=True)

    msg = 'The case number column ordinal'
    parser.add_argument('--cn', '--case-column', dest='case_column',
                        help=msg, type=int, required=False)

    msg = 'The outcome column ordinal'
    parser.add_argument('--oc', '--outcome-column', dest='outcome_column',
                        help=msg, type=int, required=False)

    msg = 'The delimiter of the original file'
    parser.add_argument('--del', '--delimiter', dest='delimiter', help=msg,
                        type=str, default=',', required=False)

    args = parser.parse_args()
    return args

def check_file_args(args, args_ok):
    """
    Check the program arguments that are input file names.

    These are needed whether we are creating training/validation sets or
    creating generic sets.
    """

    if not os.path.isfile(args.original_file_name):
        msg = '\nOriginal data set file "{0}" does not exist.\n'
        msg = msg.format(args.original_file_name)
        print(msg)
        args_ok = False

    if not os.path.isfile(args.original_data_file_info):
        msg = '\nThe orginal data file infoi file "{0}" does not exist.\n'
        msg = msg.format(args.original_data_file_info)
        print(msg)
        args_ok = False

    return args_ok

def check_unallowed_arg(set_type, arg_val, arg_name, args_ok):

    """
    Check an argument for being specified when it shouldn't be.

    set_type is the type of sets being created, ex. generic or
    training/validation. For error messages.

    arg_val is the argument value. If not None it is considered specified.
    Note that this won't work if an argument has a default value.

    arg_name is the name of the argument, for error messages.

    args_ok is the current argument check state. This is set to False if
    the argument was specified.
    """

    if arg_val is not None:
        msg = 'Creating {} sample sets was specified but {} was'
        msg += ' specified with value {}.'
        print(msg.format(set_type, arg_name, arg_val))
        args_ok = False

    return args_ok

def check_required_arg(set_type, arg_val, arg_name, args_ok):

    """
    Check an argument for being not specified when it should be.

    set_type is the type of sets being created, ex. generic or
    training/validation. For error messages.

    arg_val is the argument value. If None it is considered unspecified.
    Note that this won't work if an argument has a default value.

    arg_name is the name of the argument, for error messages.

    args_ok is the current argument check state. This is set to False if
    the argument was not specified.
    """

    if arg_val is None:
        msg = 'Creating {} sample sets was specified but {} was'
        msg += ' not specified.'
        print(msg.format(set_type, arg_name, arg_val))
        args_ok = False

    return args_ok

def check_generic_args(args, args_ok):

    """
    Creating generic sets is mutually exclusive with creating
    training/validation sets.
    """

    args_ok = check_required_arg('generic', args.generic_row_count,
                                 'generic_row_count', args_ok)

    if args.generic_row_count is not None and  args.generic_row_count < 1:
        msg = 'The generic row count, {0}, is less than 1.'
        msg = msg.format(args.generic_row_count)
        print(msg)
        args_ok = False

    args_ok = check_unallowed_arg('generic', args.training_percent,
                                  'training_percent', args_ok)

    args_ok = check_unallowed_arg('generic', args.training_row_count,
                                  'training_row_count', args_ok)

    args_ok = check_unallowed_arg('generic', args.validation_row_count,
                                  'validation_row_count', args_ok)

    args_ok = check_unallowed_arg('generic', args.column_set_file_name,
                                  'column_set_file_name', args_ok)

    args_ok = check_unallowed_arg('generic', args.column_set_start,
                                  'column_set_start', args_ok)

    return args_ok

def check_training_args(args, args_ok):
    """
    Creating training/validation sets is mutually exclusive with creating
    generic sets.
    """

    args_ok = check_required_arg('training/validation', args.training_percent,
                                 'training_percent', args_ok)

    if (args.training_percent is not None and
        (args.training_percent <= 0.0 or args.training_percent >= 1.0)):

        msg = 'Training percent should between 0 and 1, exclusive, i.e. (0,1).\n'
        print(msg)
        args_ok = False

    args_ok = check_required_arg('training/validation', args.training_row_count,
                                 'training_row_count', args_ok)

    if args.training_row_count is not None and args.training_row_count < 1:
        msg = 'The training row count, {0}, is less than 1.'
        msg = msg.format(args.training_row_count)
        print(msg)
        args_ok = False

    args_ok = check_required_arg('training/validation', args.validation_row_count,
                                 'validation_row_count', args_ok)

    if args.validation_row_count is not None and args.validation_row_count < 1:
        msg = 'The validation row count, {0}, is less than 1.'
        msg = msg.format(args.validation_row_count)
        print(msg)
        args_ok = False

    if args.column_set_file_name is not None and \
       not os.path.isfile(args.column_set_file_name):
        msg = '\nColumn set file "{0}" does not exist.\n'
        msg = msg.format(args.column_set_file_name)
        print(msg)
        args_ok = False

    # The case column and output column are requried for training and
    # validation sets but are optional for generic sets. So their values
    # are checked later.
    args_ok = check_required_arg('training/validation', args.case_column,
                                 'case_column', args_ok)

    args_ok = check_required_arg('training/validation', args.outcome_column,
                                 'outcome_column', args_ok)

    # The column set file and column set start are optional for training and
    # validation sets. If one of those is specified the other must also be
    # specified.
    if args.column_set_file_name is not None:

        if args.column_set_start is None:
            msg = 'A column set file was specified, {},'
            msg += ' but no column set start was specified'
            msg = msg.format(args.column_set_file_name)
            print(msg)
            args_ok = False

        if not os.path.isfile(args.column_set_file_name):
            msg = '\nColumn set file "{0}" does not exist.\n'
            msg = msg.format(args.column_set_file_name)
            print(msg)
            args_ok = False

    if args.column_set_start is not None:

        if args.column_set_file_name is None:
            msg = 'A column set start was specified, {},'
            msg += ' but no column set file was specified'
            msg = msg.format(args.column_set_start)
            print(msg)
            args_ok = False

        if args.column_set_start < 1:
            msg = 'The column set start, {}, is less than 1.'
            msg = msg.format(args.column_set_start)
            print(msg)
            args_ok = False

    args_ok = check_unallowed_arg('training/validation', args.generic_row_count,
                                  'generic_row_count', args_ok)

    return args_ok

def check_args(args):

    """
    Perform validity checks on the command line arguments.
    """

    args_ok = True

    args_ok = check_file_args(args, args_ok)

    if args.set_count < 1:
        msg = 'The set count, {0}, is less than 1.'
        msg = msg.format(args.set_count)
        print(msg)
        args_ok = False

    if args.generic_row_count is not None:
        args_ok = check_generic_args(args, args_ok)
    else:
        args_ok = check_training_args(args, args_ok)

    if args.column_count < 1:
        msg = 'The column count, {0}, is less than 1.'
        msg = msg.format(args.column_count)
        print(msg)
        args_ok = False

    if args.case_column is not None and args.case_column < 1:
        msg = 'The case number column ordinal, {0}, is less than 1.'
        msg = msg.format(args.case_column)
        print(msg)
        args_ok = False

    if args.outcome_column is not None and args.outcome_column < 1:
        msg = 'The outcome column ordinal, {0}, is less than 1.'
        msg = msg.format(args.outcome_column)
        print(msg)
        args_ok = False

    if (args.case_column is not None and args.outcome_column is not None and
        args.case_column == args.outcome_column):

        msg = 'The case number column ordinal and outcome column are the'
        msg += ' same, {0}'
        msg = msg.format(args.case_column)
        print(msg)
        args_ok = False

    if not args_ok:
        sys.exit(1)

    return args

def define_and_check_args(args=None):

    """
    Define, get and check the command line options.
    """
    args = define_and_get_args(args)
    check_args(args)
    return args

def print_args(args):

    """
    For testing and debugging.
    """

    print(f'args.original_file_name: {args.original_file_name}')

    msg = 'args.original_data_file_info: {0}'
    print(msg.format(args.original_data_file_info))

    print(f'args.set_count: {args.set_count}')

    if args.set_count is not None:
        # Print the generic set specific arguments.
        print(f'args.generic_row_count: {args.generic_row_count}')
    else:
        # Print the training/validation set specific arguments.
        print(f'args.training_percent: {args.training_percent}')
        print(f'args.training_row_count: {args.training_row_count}')

        msg = 'args.validation_row_count: {0}'
        print(msg.format(args.validation_row_count))

        print(f'args.column_set_file_name: {args.column_set_file_name}')
        print(f'args.column_set_start: {args.column_set_start}')

    print(f'args.column_count: {args.column_count}')
    print(f'args.case_column: {args.case_column}')
    print(f'args.outcome_column: {args.outcome_column}')
    print(f'args.delimiter: {args.delimiter}')

    print('')

def check_args_additional(original_column_count, args):

    """
    Perform argument checks that require information read from the pickle file
    of original file info.
    """

    args_ok = True

    if (args.case_column is not None and
       args.case_column > original_column_count):

        msg = 'The case number column ordinal, {0}, is greater than the number'
        msg += ' of columns in the original file, {1}.'
        msg = msg.format(args.case_column, original_column_count)
        print(msg)
        args_ok = False

    if (args.outcome_column is not None and
        args.outcome_column > original_column_count):

        msg = 'The output column ordinal, {0}, is greater than the number'
        msg += ' of columns in the original file, {1}.'
        msg = msg.format(args.outcome_column, original_column_count)
        print(msg)
        args_ok = False

    if not args_ok:
        sys.exit(1)

# pylint:disable=too-many-statements
def get_column_set(original_column_count, args):

    """
    Get a restricted set of columns to use from a specified file.

    The file has one line per column, with 2 values:

        A column ordinal.

        A value indicating the predictive power ranking of that column.
        The columns should appear in descending order by this ranking.
        The column with the highest ranking should appear first, etc.
        However, this is not checked by this script.

    Only the requested number of columns to use (args.column_count) are read.
    """

    column_set = []
    previous_priority = float('inf')
    with open(args.column_set_file_name, 'r', encoding='utf_8') as input_file:
        ordinal_base = 1
        for (ordinal, line) in enumerate(input_file, ordinal_base):

            if ordinal > args.column_count:
                break

            # Delete trailing newline so it isn't treated as part of the values
            # read.
            fields = line.rstrip('\n').split(',')

            if len(fields) > 2:
                msg = 'Line {} of column set file {} has {} fields.'
                msg += ' Only 2 are expected.'
                msg = msg.format(ordinal, args.column_set_file_name, len(fields))
                print(msg)
                sys.exit(1)

            try:
                column = int(fields[0])
            except ValueError:
                msg = 'Column "{0}" from line {1} of file {2} is not an'
                msg += ' integer.'
                msg = msg.format(fields[0], ordinal, args.column_set_file_name)
                print(msg)
                sys.exit(1)

            try:
                priority = float(fields[1])
            except ValueError:
                msg = 'Priority "{0}" from line {1} of file {2} is not a float.'
                msg = msg.format(fields[1], ordinal, args.column_set_file_name)
                print(msg)
                sys.exit(1)

            if column < 1 or column > original_column_count:
                msg = 'Column "{0}" from line {1} of file {2} is out of range.'
                msg += ' It must be between 1 and {3}.'
                msg = msg.format(fields[0], ordinal, args.column_set_file_name, \
                                 original_column_count)
                print(msg)
                sys.exit(1)

            if column == args.case_column:
                msg = 'Column "{0}" from line {1} of file {2} is the same as'
                msg += ' the case column {3}.'
                msg = msg.format(fields[0], ordinal, args.column_set_file_name, \
                                 args.case_column)
                print(msg)
                sys.exit(1)

            if column == args.outcome_column:
                msg = 'Column "{0}" from line {1} of file {2} is the same'
                msg += ' as the output column {3}.'
                msg = msg.format(fields[0], ordinal, args.column_set_file_name, \
                                 args.outcome_column)
                print(msg)
                sys.exit(1)

            if priority > previous_priority:
                msg = 'Priority {} from line {} of column set file {}'
                msg += ' is > the priority of {} from the previous line.'
                msg = msg.format(priority, ordinal, args.column_set_file_name,
                                 previous_priority)
                print(msg)
                sys.exit(1)

            if column in column_set:
                msg = 'Column "{0}" from line {1}'
                msg += ' already appeared in file {2}.'
                msg = msg.format(fields[0], ordinal, args.column_set_file_name)
                print(msg)
                sys.exit(1)

            column_set.append(column)
            previous_priority = priority

    return column_set

def define_available_ordinals(original_line_count, args):

    """
    Define two disjoint sets of line ordinals from the original file to be
    used for sampling to create the training sets and validation sets.

    The ordinals for the data lines are shuffled, the first training_percent
    are chosen for sampling to create the training sets, and the remaining
    data ordinals used for sampling to create the validation sets.
    """

    # 2 to skip the header line.
    data_ordinals = list(range(2, original_line_count+1))

    if args.training_percent is not None:
        # Creating training and validation sets.
        random.shuffle(data_ordinals)

        data_ordinal_count = len(data_ordinals)
        training_ordinal_count = int(args.training_percent * data_ordinal_count)
        validation_ordinal_count = data_ordinal_count - training_ordinal_count

        args_ok = True
        if args.training_row_count >= training_ordinal_count:
            msg = 'The training row count, {}, is greater than the available'
            msg += ' training rows {}.'
            msg = msg.format(args.training_row_count, training_ordinal_count)
            print(msg)
            args_ok = False

        if args.validation_row_count >= validation_ordinal_count:
            msg = 'The validation row count, {}, is greater than or equal to the'
            msg += ' available validation row count of {}.'
            msg = msg.format(args.validation_row_count, validation_ordinal_count)
            print(msg)
            args_ok = False

        if not args_ok:
            sys.exit(1)

        TrainingSet.available_ordinals = data_ordinals[0:training_ordinal_count]
        ValidationSet.available_ordinals = data_ordinals[training_ordinal_count:]

    else:
        # Creating generic sets.
        # Define the full range of row ordinals of the original file as the ones to
        # use by the ValidatonSet class. 2 to skip the header line.
        ValidationSet.available_ordinals = list(data_ordinals)

def create_training_sets(original_column_count, starting_set_number, args,
                         column_set):

    """
    Create the training set and validation set objects.

    The TrainingSet constructor creates the Validation set for that
    training set.
    """

    print('Creating SelectionSet objects for training and validation sets...', end='')

    selection_sets = []

    # Create the training sets.
    ending_set_number = min(starting_set_number - 1 + args.set_count,
                            args.set_count)

    for i in range(starting_set_number, ending_set_number + 1):
        try:

            column_set_to_use = column_set
            if args.column_set_start is not None:
                # Using a column set file.
                cols = args.column_set_start + (i - 1)
                column_set_to_use = column_set[0:cols]

            tr_set = TrainingSet(i, original_column_count, args, column_set_to_use)
        except OSError as e:
            if e.errno == 24:
                # A file open error occurred.
                if len(selection_sets) > 1:
                    # Probably attempted to open too many files.
                    # On this pass of the original file process the training
                    # sets successfully opened.
                    ending_set_number = i - 1
                    break

                msg = 'A file open exception occured creating TrainingSet'
                msg +=' {0} of {1}:\n{2}'
                msg = msg.format(i, args.set_count, e)
                print(msg)
                sys.exit(1)
            else:
                msg = 'An OSError exception occured creating TrainingSet {0} of {1}:\n{2}'
                msg = msg.format(i, args.set_count, e)
                print(msg)
                sys.exit(1)
        # pylint: disable=broad-exception-caught
        except Exception as e:
            msg = 'An exception occured creating TrainingSet {0} of {1}:\n{2}'
            msg = msg.format(i, args.set_count, e)
            print(msg)
            sys.exit(1)

        selection_sets.append(tr_set)

    print('...Done')
    return selection_sets, ending_set_number

def create_generic_sets(original_column_count, starting_set_number, args,
                        column_set):

    """
    Create the generic set objects.

    We use the ValidationSet for this since they have the necessary
    functionality, so new set class is needed. TrainingSet won't work
    because creating a TrainingSet also creates a ValidationSet, and we
    only need one SelectionSet for each generic set.
    """

    print('Creating SelectionSet objects for generic sets...', end='')

    if column_set is not None:
        # Generic sets can't use a column set, so one should not have been
        # specified.
        msg = 'Creating generic sets but a column set was specified.'
        print(msg)
        sys.exit(1)

    selection_sets = []

    # Create the training sets.
    ending_set_number = min(starting_set_number - 1 + args.set_count, args.set_count)

    for i in range(starting_set_number, ending_set_number + 1):
        try:
            val_set = ValidationSet(i, original_column_count, args,
                                    args.generic_row_count, column_set,
                                    'set-')
        except OSError as e:
            if e.errno == 24:
                # A file open error occurred.
                if len(selection_sets) > 1:
                    # Probably attempted to open too many files.
                    # On this pass of the original file process the training
                    # sets successfully opened.
                    ending_set_number = i - 1
                    break

                msg = 'A file open exception occured creating ValidationSet'
                msg +=' {0} of {1}:\n{2}'
                msg = msg.format(i, args.set_count, e)
                print(msg)
                sys.exit(1)
            else:
                msg = 'An OSError exception occured creating ValidationSet {0} of {1}:\n{2}'
                msg = msg.format(i, args.set_count, e)
                print(msg)
                sys.exit(1)
        # pylint: disable=broad-exception-caught
        except Exception as e:
            msg = 'An exception occured creating ValidationSet {0} of {1}:\n{2}'
            msg = msg.format(i, args.set_count, e)
            print(msg)
            sys.exit(1)

        selection_sets.append(val_set)

    print('...Done')
    return selection_sets, ending_set_number

def create_selection_sets(original_column_count, starting_set_number, args,
                          column_set):

    """
    Create the SelectionSet objects needed for sampling.
    """

    if args.training_percent is not None:
        # Doing training and validation sets.
        selection_sets, ending_set_number = create_training_sets(
                                                original_column_count,
                                                starting_set_number, args,
                                                column_set)
    else:
        # Doing generic sets.
        selection_sets, ending_set_number = create_generic_sets(
                                                original_column_count,
                                                starting_set_number, args,
                                                column_set)

    return selection_sets, ending_set_number

def process_original_file(input_file, selection_sets, delimiter):

    """

    Process each line from input_file.

    input_file is an open file object.
        If it is a file being read from a zip file, the lines read will be byte
        objects, which will need to be converted to string objects.

    Each line is passed to each selection set. If the ordinal for that line is
    one of the row ordinals for a selection set the selection set writes it to
    its set file (training set file for a training set, validation set file for
    a validation set.

    """

    # Count the line ordinals starting from 1, not the default of 0.
    option_base = 1
    for (ordinal, line) in enumerate(input_file, option_base):

        # If reading from a zip file, convert from bytes to string.
        if isinstance(line, bytes):
            line = line.decode('utf-8')

        # Used for debugging.
        #if ordinal == 1:
            #header = line

        if line.find(delimiter) == -1:
            msg = f'The delimiter, "{delimiter}" was not found in line\n {line}'
            print(msg)
            sys.exit(1)

        # Delete trailing newline from last column, otherwise, if the last
        # column is written to a training set then that training set will have
        # extra blank lines.
        line_fields = line.rstrip('\n').split(delimiter)

        #if len(line_fields) != original_column_count:
            #msg = 'Line {0} has {1} columns, which doesn''t match'
            #msg += ' the header line, which has {2} columns.'
            #msg += '\nHeader line:\n{3}'
            #msg += '\nline {0}:\n{4}'
            #msg = msg.format(ordinal, len(line_fields), original_column_count, \
                             #header, line)
            #print(msg)
            #sys.exit(0)

        for sel_set in selection_sets:
            sel_set.check_line(ordinal, line_fields)

@contextmanager
def get_original_file_object(original_file_name):
    """
    Get and return a file object to the original data file,
    even if it is in a zip file.

    This function is decorated as a contextmanager, so it can be used in
    a with statement:
    with get_original_file_object(some_file_name) as input_file:
        process input_file
    """

    if original_file_name.endswith('.zip'):
        zip_file, regular_file = get_original_from_zip(original_file_name)
        try:
            yield regular_file
        finally:
            regular_file.close()
            zip_file.close()
    else:
        regular_file = open(original_file_name, 'r', encoding='utf_8')
        try:
            yield regular_file
        finally:
            regular_file.close()

def get_original_from_zip(zip_file_name):

    """
    Get a file object for reading the original file from zip file.

    The csv file in the zip file will be read directly from the zip archive,
    without having to extract it.

    The regular file name is assumed to be the same as the zip file name
    but ending with ".csv" instead of ".zip" and no path.
    """

    # pylint: disable=consider-using-with
    zfile = zipfile.ZipFile(zip_file_name, 'r')


    # Delete the path, everything up to the last '/', if there is one.
    regular_file_name = zip_file_name
    slash_index = regular_file_name.rfind('/')
    if slash_index > 0:
        regular_file_name = regular_file_name[slash_index+1:]

    # Change the suffix from 'zip' to 'csv'. Don't use rstrip. it should
    # work, but it doesn't remove a specific string, but any sequence of
    # characters in that string.  'abc.pizzip'.rstrip('zip') results in
    # 'abc.'. String function replace would replace all occurences of
    # 'zip', ex.  'zip-of-abc.zip'.replace('zip', 'csv') becomes
    # 'csv-of-abc.csv'. String function removesuffix isn't available before
    # Python3 version 3.9, so it isn't always available on all production
    # systems.
    regular_file_name = regular_file_name[:-3] + 'csv'
    #print(f'regular_file_name {regular_file_name}')

    try:
        # pylint: disable=consider-using-with
        regular_file = zfile.open(regular_file_name)
    except IOError as e:
        msg = '\nThe following exception occured opening'
        msg += ' zip file member {} from zip file {}\n{}'
        msg = msg.format(regular_file_name, zip_file_name, e)
        print(msg)
        sys.exit(1)

    return zfile, regular_file

def close_selection_sets(selection_sets):

    """
    Close the open file for each selection set.
    """

    for selset in selection_sets:
        selset.close()

# pylint: disable=too-many-locals
def program_start():
    """
    The main function for the program.

    Putting this code in a function rather than in global scope simplifies
    using pylint. It avoids many pylint complaints such as redfining a variable
    from an outer scope or insisting a variable name refers to a constant
    (pyling considers a constant any variable defined at module level that is
     not bound to a class object).
    """

    total_tic = time.perf_counter()

    args = define_and_check_args()
    #print_args(args)

    # Load the original file info.
    with open(args.original_data_file_info, 'rb') as odi_file:
        (original_line_count, original_column_count) = pickle.load(odi_file)

    check_args_additional(original_column_count, args)

    # If requested get a restricted set of column ordinals to use.
    column_set = None
    if args.column_set_file_name is not None:
        column_set = get_column_set(original_column_count, args)

        column_set_count = len(column_set)
        if column_set_count < args.column_count:
            msg += 'The number of columns, {}, from the column set file'
            msg += ' {} is less than the specified column count of {}.'
            msg = msg.format(column_set_count, args.column_set_file_name,
                             args.column_count)
            print(msg)
            sys.exit(1)

        set_count_limit = len(column_set) - args.column_set_start + 1
        if args.set_count > set_count_limit:
            msg = 'The set count of {} is greater than the number of sets'
            msg += ' supportable, {}, by the column set start of {} and the'
            msg += ' column count of {}.'
            msg = msg.format(args.set_count, set_count_limit,
                             args.column_set_start, args.column_count)
            print(msg)
            sys.exit(1)

    # Define a partition the original file into two disjoint sets of row
    # ordinals, one for training sets and one for validation sets.
    define_available_ordinals(original_line_count, args)

    # Process the original file using as many passes as necessary,
    # given the system limit on the macimum number of open files.
    starting_set_number = 1
    ending_set_number = 0
    file_pass_count = 0
    while ending_set_number < args.set_count:

        tic = time.perf_counter()
        file_pass_count += 1
        print(f'\nPerforming pass {file_pass_count} of {args.original_file_name}')

        # Get a file object to the original file, open for reading.
        # This must come before creating the selection sets to avoid a
        # "too many open files" error. If the creation of the selection sets
        # uses up the available open files, then attempting to open the
        # original file would cauase a "too many open files" error. Opening
        # the original file first accounts for that open file, then we can
        # open as many selection sets as allowed from the remaining open file
        # slots.
        with get_original_file_object(args.original_file_name) as input_file:

            # Create as many SelectionSet objects as allowed by the
            # system limit on number of open files.
            (selection_sets, ending_set_number) = create_selection_sets(
                                                      original_column_count,
                                                      starting_set_number, args,
                                                      column_set)

            msg = 'Creating SelectionSet files {} to {} ...'
            print(msg.format(starting_set_number, ending_set_number), end='')
            process_original_file(input_file, selection_sets, args.delimiter)

        close_selection_sets(selection_sets)
        print('...Done')

        # For generic sets this is the total number of sets in the pass.
        # For training/validation sets it is the number of training sets,
        # not the number of training sets + number of validation sets.
        pass_set_count = ending_set_number - starting_set_number + 1

        toc = time.perf_counter()
        pass_time = toc - tic
        set_time = pass_time / pass_set_count
        msg = f'Pass {file_pass_count} took {pass_time:.0f} seconds,'
        msg += f' {set_time:.0f} seconds per set for {pass_set_count} sets.'
        print(msg)

        starting_set_number = ending_set_number + 1

    total_toc = time.perf_counter()
    print(f'\n{file_pass_count} passes completed in {total_toc - total_tic:.0f} seconds')

if __name__ == '__main__':
    program_start()
