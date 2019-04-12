#!-*- coding:utf-8 -*-
#
# 2018/10/12 modified from 
#     parsePythonValue.py
#     Copyright, 2006, by Paul McGuire
# modifications:
#   - run for py2 and py3
#   - variable key (without quotes) in a dict
# reason:
#   - lepl has memory leak problem, this is going to replace it in the future.
#
from __future__ import print_function
from pyparsing import *
import sys
PY3 = sys.version_info[0] == 3

cvtBool = lambda t:t[0]=='True'
cvtInt = lambda toks: int(toks[0])
cvtReal = lambda toks: float(toks[0])
cvtTuple = lambda toks : tuple(toks.asList())
cvtDict = lambda toks: dict(toks.asList())
cvtList = lambda toks: [toks.asList()]

# define punctuation as suppressed literals
lparen,rparen,lbrack,rbrack,lbrace,rbrace,colon = \
    map(Suppress,"()[]{}:")


integer = Regex(r"[+-]?\d+")\
    .setName("integer")\
    .setParseAction( cvtInt )
real = Regex(r"[+-]?\d+\.\d*([Ee][+-]?\d+)?")\
    .setName("real")\
    .setParseAction( cvtReal )
tupleStr = Forward()
listStr = Forward()
dictStr = Forward()

if PY3:
    unicodeString.setParseAction(lambda t:t[0][2:-1])
    quotedString.setParseAction(lambda t:t[0][1:-1])
else:
    unicodeString.setParseAction(lambda t:t[0][2:-1].decode('unicode-escape'))
    quotedString.setParseAction(lambda t:t[0][1:-1].decode('string-escape'))

boolLiteral = oneOf("True False").setParseAction(cvtBool)
noneLiteral = Literal("None").setParseAction(replaceWith(None))

listItem = real|integer|quotedString|unicodeString|boolLiteral|noneLiteral| \
            Group(listStr) | tupleStr | dictStr

tupleStr << ( Suppress("(") + Optional(delimitedList(listItem)) + 
            Optional(Suppress(",")) + Suppress(")") )
tupleStr.setParseAction( cvtTuple )

listStr << (lbrack + Optional(delimitedList(listItem) + 
            Optional(Suppress(","))) + rbrack)
listStr.setParseAction(cvtList, lambda t: t[0])

# if want to allow {c:'1'} style of dict
'''
variable = Word( alphas) #key of dict
dictKey = variable | listItem
dictEntry = Group( dictKey + colon + listItem )
'''
dictEntry = Group( listItem + colon + listItem )

dictStr << (lbrace + Optional(delimitedList(dictEntry) + \
    Optional(Suppress(","))) + rbrace)
dictStr.setParseAction( cvtDict )

commaSeperatedArgs = tupleStr

if __name__ == '__main__':
    tests = """['a', 100, ('A', [101,102]), 3.14, [ +2.718, 'xyzzy', -1.414] ]
               [{0: [2], 1: []}, {0: [], 1: [], 2: []}, {0: [1, 2]}]
               { 'A':1, 'B':2, 'C': {'a': 1.2, 'b': 3.4} }
               3.14159
               42
               6.02E23
               6.02e+023
               1.0e-7
               [None,1]
               None
               {'f':2, 'p':'I_Ycyp41ejGmnASG8J8Gs_v4pdaafAdjjS2TpeWRLSYdD9t4q1o4879-O_7CrHrx6BSrNzsbzZaMdUHQkzNHCtNIKwMeywBKltlXaI_aZfQVWqi7bt4O2vhqqmo3Iy5LXJ8S0Sdqja3j7d84xbat0G3nPxntDxlJyO-SYf44grA', 't':'A', 'i':-1, 'c':'#BF1260'}
               'a quoted string'
               { 'A':1, 'B':2, 'C': {'a': 1.2, 'b': 3.4} }
               """.split("\n")

    tests = [
                '1',
                '2.0, 3, "\\n"',
                'True, False, 4,\'5\',"6,7- -8","\\9 10"',
                #'(1,2,x=3,y=4,z=5)',
                '1,(2,3),(4,5,6),[7],[8,9],{"a":"b"},{"c":"d","e":"f"}',#,x=(2,3),y=[4,5,6],z={7:8}',
                '{\'c\':1,\'d\':[2,3]}',
                '("a","b",{"c":1,"d e":1})',
                '("a","b",{"c":1,"d e":[2,[3,4],[5,{6:7,8:9}]]})',
                '("a","b",{"c":1,"d e":[2,[3,4],[5,{6:7,8:[10,"11 12"]}]]})',
                '{"c":1,"d e f":2, "ghi":"j"}',
                """{'f':2, 'p':'I_Ycyp41ejGmnASG8J8Gs_v4pdaafAdjjS2TpeWRLSYdD9t4q1o4879-O_7CrHrx6BSrNzsbzZaMdUHQkzNHCtNIKwMeywBKltlXaI_aZfQVWqi7bt4O2vhqqmo3Iy5LXJ8S0Sdqja3j7d84xbat0G3nPxntDxlJyO-SYf44grA', 't':'A', 'i':-1, 'c':'#BF1260'}""",
                #'("abc","defg","hello world","I am   \\"very\\"    fine","我都OK")'
            ]
    #tests = [
    #    '(1,2,x=3,y=4,z=5)' # **kw not supported
    #    ]
    for test in tests:
        print("Test:", test.strip())
        if not test[0]=='(': test = '('+test+')'
        parse_result = commaSeperatedArgs.parseString(test)
        print("Result result:", type(parse_result),parse_result)
        result = parse_result[0]
        print("Result:", type(result))
        for item in result:
            print()
            print('\t',type(item),item)
            print()
