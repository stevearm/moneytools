import argparse
from collections import defaultdict, namedtuple
import csv
from datetime import datetime
from decimal import Decimal
import functools
import operator
import re

import piecash

VERBOSE=False
TOLERANT=False

def main():
    parser = argparse.ArgumentParser(description="Create a GNUCash book from YNAB export")
    parser.add_argument("--verbose", action="store_true", help="Print lots of messages")
    parser.add_argument("--tolerant", action="store_true", help="Tolerate strange transactions")
    parser.add_argument("register", help="Register csv to read from")
    parser.add_argument("--book", default="book.gnucash", help="Output file to overwrite")
    args = parser.parse_args()

    global VERBOSE
    VERBOSE=args.verbose
    global TOLERANT
    TOLERANT=args.tolerant

    book = piecash.create_book(sqlite_file=args.book, overwrite=True, currency="USD")

    importRegister(book, args.register)
    book.save()


def tolerableError(message):
    if not TOLERANT:
        raise Exception(message)
    print(message)


def importRegister(book, register):
    printOnceSet = set()
    def printOnce(tag, message):
        if tag in printOnceSet:
            return
        # printOnceSet.add(tag)
        print(message)

    transfers = list()

    for entry in readRegister(register):
        # Gather general info
        account = getBankAccount(book, entry.account)
        entryDateTime = datetime.strptime(entry.date, "%m/%d/%Y")
        categoryGroup = entry.categoryGroup
        category = entry.category
        description = entry.payee
        if len(entry.memo) < 0:
            description = "{} - {}".format(description, entry.memo)

        # Figure out balance adjustment
        inflow = Decimal(entry.inflow[1:])
        outflow = Decimal(entry.outflow[1:])
        netflow = inflow - outflow
        if inflow != Decimal() and outflow != Decimal():
            raise Exception("Single entry with inflow and outflow: {}".format(entry))

        # Process entry
        if entry.payee == "Starting Balance":
            if netflow != Decimal():
                if VERBOSE:
                    print("Creating starting balance of {} for {}".format(netflow, account))
                # Maintain: Assets - Liabilities = Equity + (Income - Expenses)
                createTransaction(book, entryDateTime, dict(description="Starting Balance", splits=[
                                  dict(account=getStartingBalanceAccount(book), value=-netflow),
                                  dict(account=account, value=netflow)]))
                optimizedSave(book)
        elif entry.payee.startswith("Transfer : "):
            otherAccount = entry.payee[len("Transfer : "):]
            if netflow == Decimal():
                raise Exception("Transfers of $0 make no sense".format(entry))
            if netflow > Decimal():
                fromAccount = otherAccount
                toAccount = entry.account
                amount = netflow
                action = "recieve"
            else:
                fromAccount = entry.account
                toAccount = otherAccount
                amount = -netflow
                action = "send"

            # Add to transfers: (entryDateTime, fromString, toString, amount, action)
            transfers.append((entryDateTime, fromAccount, toAccount, amount, action))

        elif categoryGroup == "Inflow":
            if category != "To be Budgeted":
                raise Exception("Unexpected inflow: {}".format(entry))
            if outflow != Decimal():
                tolerableError("Inflow: To be Budgeted shouldn't have outflow: {}".format(entry))
            if netflow == Decimal():
                raise Exception("Inflow shouldn't have 0 balance: {}".format(entry))
            createTransaction(book, entryDateTime, dict(description=description, splits=[
                              dict(account=getIncomeAccount(book, entry.payee), value=-netflow),
                              dict(account=account, value=netflow)]))
        elif categoryGroup in ["Everyday Expenses",
                               "Long term",
                               "Yearly Fees",
                               "Hidden Categories",
                               "Monthly Bills",
                               "Trips"]:
            if netflow == Decimal():
                tolerableError("Expense shouldn't have 0 money flow: {}".format(entry))

            createTransaction(book, entryDateTime, dict(description=description, splits=[
                              dict(account=getExpenseAccount(book, categoryGroup, category), value=-netflow),
                              dict(account=account, value=netflow)]))
        elif categoryGroup == "":
            incomeAccount, expenseAccount = getUncategorized(book)
            if netflow > Decimal():
                otherAccount = incomeAccount
            else:
                otherAccount = expenseAccount
            createTransaction(book, entryDateTime, dict(description=description, splits=[
                              dict(account=otherAccount, value=-netflow),
                              dict(account=account, value=netflow)]))
        else:
            raise Exception("Unexpected row: {}".format(entry))

    # Handle transfers (entryDateTime, fromString, toString, amount, action)
    for index in range(len(transfers[0]) - 1, -1, -1):
        transfers = sorted(transfers, key=operator.itemgetter(index))
    while len(transfers) > 0:
        if len(transfers) == 1:
            raise Exception("Unbalanced transfers: {}".format(transfers[0]))
        first = transfers[0]
        second = transfers[1]
        transfers = transfers[2:]
        for index in range(4):
            if first[index] != second[index]:
                raise Exception("These transfers aren't paired: {} - {}".format(first, second))
        if sorted([first[-1], second[-1]]) != ["recieve", "send"]:
            raise Exception("These transfers aren't double ended: {} - {}".format(first, second))
        createTransaction(book, entryDateTime, dict(description="Transfer", splits=[
                          dict(account=getBankAccount(book, first[1]), value=-first[3]),
                          dict(account=getBankAccount(book, first[2]), value=first[3])]))


def getStartingBalanceAccount(book):
    return getAccount(book, [("Equity", dict(type="EQUITY", placeholder=True)),
                             ("Opening Balances", dict(type="EQUITY"))])


def getBankAccount(book, name):
    return getAccount(book, [("Assets", dict(type="ASSET", placeholder=True)),
                             ("Current Assets", dict(type="ASSET", placeholder=True)),
                             (name, dict(type="ASSET"))])


def getExpenseAccount(book, categoryGroup, category):
    return getAccount(book, [("Expense", dict(type="EXPENSE", placeholder=True)),
                             (categoryGroup, dict(type="EXPENSE", placeholder=True)),
                             (category, dict(type="EXPENSE"))])


def getIncomeAccount(book, source):
    source = source.replace(":", "_")
    return getAccount(book, [("Income", dict(type="INCOME", placeholder=True)),
                             (source, dict(type="INCOME"))])


def getUncategorized(book):
    income = getAccount(book, [("Income", dict(type="INCOME", placeholder=True)),
                               ("Uncategorized", dict(type="INCOME"))])
    expense = getAccount(book, [("Expense", dict(type="EXPENSE", placeholder=True)),
                                ("Uncategorized", dict(type="EXPENSE"))])
    return income, expense


def getAccount(book, names):
    account = book.root_account
    for name, args in names:
        try:
            account = account.children(name=name)
        except KeyError:
            args["name"] = name
            args["parent"] = account
            args["commodity"] = book.default_currency
            account = piecash.Account(**args)
            optimizedSave(book)
    return account


def createTransaction(book, entryDateTime, args):
    args["currency"] = book.default_currency
    args["post_date"] = entryDateTime.date()
    args["enter_date"] = entryDateTime
    splitArgs = args["splits"]
    args["splits"] = []
    for splitArg in splitArgs:
        args["splits"].append(piecash.Split(**splitArg))
    piecash.Transaction(**args)
    optimizedSave(book)


__optimizedSaveCounter = 0
def optimizedSave(book):
    global __optimizedSaveCounter
    if __optimizedSaveCounter <= 0:
        __optimizedSaveCounter = 100
        book.save()
    __optimizedSaveCounter -= 1


def readRegister(filename):
    with open(filename, "r") as fileHandle:
        reader = csv.reader(fileHandle)
        header = next(reader)

        # The first column has garbage in it for some reason
        match = re.match(r"^[^\"]+\"(.+)\"$", header[0])
        if match:
            header[0] = match.group(1)

        if header != ["Account", "Flag", "Date", "Payee", "Category Group/Category", "Category Group", "Category", "Memo", "Outflow", "Inflow", "Cleared"]:
            raise Exception("Unknown format: {}".format(header))

        RegisterEntry = namedtuple("RegisterEntry", ["account", "date", "payee", "categoryGroup", "category", "memo", "outflow", "inflow"])
        for row in reader:
            yield RegisterEntry(row[0], *row[2:4], *row[5:10])


if __name__ == "__main__":
    main()
