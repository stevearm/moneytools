import argparse
from collections import defaultdict
import csv
import re

import piecash

VERBOSE=False

def main():
    parser = argparse.ArgumentParser(description="Create a GNUCash book from YNAB export")
    parser.add_argument("--verbose", action="store_true", help="Print lots of messages")
    parser.add_argument("--budget", required=True, help="Budget csv to read from")
    parser.add_argument("--book", default="book.gnucash", help="Output file to overwrite")
    args = parser.parse_args()

    global VERBOSE
    VERBOSE=args.verbose

    book = piecash.create_book(sqlite_file=args.book, overwrite=True, currency="USD")

    createAccountsForCategories(book, args.budget)


def createAccountsForCategories(book, budgetCsv):
    groups = defaultdict(set)
    for rowDict in readCsvDict(budgetCsv):
        groups[rowDict["Category Group"]].add(rowDict["Category"])

    if VERBOSE:
        print("{} groups with a total of {} categories".format(
            len(groups),
            sum([len(groups[x]) for x in groups.keys()])))

    currency = book.default_currency
    expensesAccount = piecash.Account(name="Expenses",
                                      type="EXPENSE",
                                      parent=book.root_account,
                                      commodity=currency,
                                      placeholder=True,)
    for group, categories in groups.items():
        groupAccount = piecash.Account(name=group,
                                       type="EXPENSE",
                                       parent=expensesAccount,
                                       commodity=currency,
                                       placeholder=True,)
        for category in categories:
            piecash.Account(name=category,
                            type="EXPENSE",
                            parent=groupAccount,
                            commodity=currency)
    book.save()


def readCsvDict(filename):
    with open(filename, "r") as fileHandle:
        reader = csv.reader(fileHandle)
        header = next(reader)

        # The first column has garbage in it for some reason
        match = re.match(r"^[^\"]+\"(.+)\"$", header[0])
        if match:
            header[0] = match.group(1)

        for row in reader:
            yield dict(zip(header, row))


if __name__ == "__main__":
    main()
