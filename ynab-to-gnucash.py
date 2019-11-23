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
    parser.add_argument("--register", required=True, help="Register csv to read from")
    parser.add_argument("--book", default="book.gnucash", help="Output file to overwrite")
    args = parser.parse_args()

    global VERBOSE
    VERBOSE=args.verbose

    book = piecash.create_book(sqlite_file=args.book, overwrite=True, currency="USD")

    createAccountsForCategories(book, args.budget)
    createAccountsForTransactions(book, args.register)


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


def createAccountsForTransactions(book, registerCsv):
    accounts = set()
    incomeSources = set()
    for rowDict in readCsvDict(registerCsv):
        accounts.add(rowDict["Account"])
        if rowDict["Category Group/Category"] == "Inflow: To be Budgeted":
            if rowDict["Payee"] != "Starting Balance":
                incomeSources.add(rowDict["Payee"])
        else:
            pass

    if VERBOSE:
        print("{} asset accounts".format(len(accounts)))
        print("{} income sources".format(len(incomeSources)))

    currency = book.default_currency

    # Create bank accounts
    account = piecash.Account(name="Assets",
                              type="ASSET",
                              parent=book.root_account,
                              commodity=currency,
                              placeholder=True)
    account = piecash.Account(name="Current Assets",
                              type="ASSET",
                              parent=account,
                              commodity=currency,
                              placeholder=True)
    for accountName in accounts:
        piecash.Account(name=accountName,
                        type="ASSET",
                        parent=account,
                        commodity=currency)

    # Create equity account for starting balances
    account = piecash.Account(name="Equity",
                              type="EQUITY",
                              parent=book.root_account,
                              commodity=currency,
                              placeholder=True)
    account = piecash.Account(name="Opening Balances",
                              type="EQUITY",
                              parent=account,
                              commodity=currency)

    # Create income accounts
    account = piecash.Account(name="Income",
                              type="INCOME",
                              parent=book.root_account,
                              commodity=currency,
                              placeholder=True)
    for accountName in incomeSources:
        piecash.Account(name=accountName,
                        type="INCOME",
                        parent=account,
                        commodity=currency)

    book.save()


def thing():
    if "Payee" in rowDict:
        if rowDict["Payee"] == "Starting Balance":
            del rowDict["Category Group"]
            del rowDict["Category"]
            del rowDict["Date"]
            print(rowDict)
            if rowDict["Outflow"] != "$0.00":
                print("ASDF")
                # break
            if rowDict["Memo"] != "":
                print("ASDF")


def importTransactions(book, registerCsv):
    tr2 = Transaction(currency=book.default_currency,
                      description="transfer 2",
                      splits=[Split(account=a1, value=-100),
                              Split(account=a2, value=100, quantity=30)
                              ])


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
