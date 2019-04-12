#! -*- coding:utf-8 -*-

# API:http://www.acooke.org/lepl/api/index.html
# Download lepl at https://github.com/cajus/python-lepl
import lepl
lepl.support.warn.silence('SignedEFloat')
from lepl import (Drop, Literal, Word,Digit, Float, 
   Integer,String,Whitespace,Letter,Separator,Regexp,Delayed, 
    Eos, Node, Space, DroppedSpace)

def create_parser(delimiter):
    space  = Space()
    comma  = Drop(',') | Drop(',')+space

    if delimiter==',':
        # by comma
        seperator =  Separator(~Regexp(r'\s*'))

        delimiter = comma
    else:
        assert delimiter == ' ', 'delimiter "%s" not supported' % delimiter
        seperator =  DroppedSpace()
        delimiter = space

    none   = Literal('None')                        >> (lambda x: None)
    bool   = (Literal('True') | Literal('False'))   >> (lambda x: x == 'True')
    ident  = Word(Letter() | '_',
                  Letter() | '_' | Digit())
    float_ = Float()                                >> float
    int_   = Integer()                              >> int
    str_   = String() | String("'")

    dict_key =  str_| int_ | float_ | Word()
    dict_spaces = ~Whitespace()[:]
    dict_value = dict_key

    item   = str_ | int_ | float_ | none | bool | ident | Word()

    with seperator:
        value  = Delayed()
        list_  = Drop('[')  & value[:, comma]   & Drop(']') > list
        tuple_ = Drop('(')  & value[:, comma]  & Drop(')') > tuple

        dict_el = dict_key & Drop(':') & value > tuple
        dict_ = Drop ('{') & dict_el[1:,Drop(',')] & Drop ('}') > dict

        value += list_ | tuple_ | dict_ | item | space

        arg    = value                                     >> 'arg'
        karg   = (ident & Drop('=') & value                > tuple) >> 'karg'
        expr   = (karg | arg)[:, delimiter] & Drop(Eos())  > Node
    
    return expr.get_parse()

command_line_parser = {',':None,' ':None}
def parse_line(line,delimiter=','):
    if line == '': return []
    if command_line_parser[delimiter] is None:
        command_line_parser[delimiter] = create_parser(delimiter)
    ast = command_line_parser[delimiter](line)
    args = []
    try:
        for n in ast[0].arg:
            args.append(n)
    except AttributeError:
        pass
    try:
        kargs = {}
        for n in ast[0].karg:
            kargs[n[0]] = n[1]
        args.append(kargs)
    except AttributeError:
        pass
    return args

if __name__ == '__main__':
    import pprint,sys
    pp = pprint.PrettyPrinter()
    if 0:
        tests = [
            "call(1, 2)",
        ]
        delimiter = ' '
    elif 0:
        tests = [
            "asia/taipei 2",
            '1',
            '2.0 3',
            'a=b c=d',
            '1 2 "3 4" (5,6) {name: asia-taipei}'
        ]
        delimiter = ' '
    elif 0:
        tests = ["a=1,{a:3},{'a':2},{\"a\":1}",
            '\'{"a": "b", "c": "d"}\''
        ]
        delimiter = ','
    elif 0:
        tests = [
            '1',
            '2.0, 3',
            'True, False, "4",\'5\',"6,7- -8","\\9 10"',
            '1,2,x=3,y=4,z=5',
            '1,(2,3),(4,5,6),[7],[8,9],{"a":"b"},{"c":"d","e":"f"},x=(2,3),y=[4,5,6],z={7:8}',
            '{\'c\':1,\'d\':[2,3]}',
            'a,b,{"c":1,"d e":[2,[3,4],[5,{6:7,8:9}]]}',
            'a,b,{"c":1,"d e":[2,[3,4],[5,{6:7,8:[10,"11 12"]}]]}',
            '{c:1,"d e f":2, ghi:"j"}',
            u'abc,defg,"hello world","I am   \\"very\\"    fine","我都OK"'
        ]
        delimiter = ','
    elif 0:
        tests = [
            '1',
            '2.0 3',
            'True False "4" \'5\' "6,7- -8" "\\9 10"',
            '1 2 x=3 y=4 z=5',
            '1 (2,3) (4,5,6) [7] [8,9] {"a":"b"} {"c":"d","e":"f"} x=(2,3) y=[4,5,6] z={7:8}',
            '{\'c\':1,\'d\':[2,3]}',
            'a b {"c":1,"d e":[2,[3,4],[5,{6:7,8:9}]]}',
            'a b {"c":1,"d e":[2,[3,4],[5,{6:7,8:[10,"11 12"]}]]}',
            '{c:1,"d e f":2, ghi:"j"}',
            'abc defg "hello world"     "I am   \\"very\\"    fine" "我都OK"'
        ]
        delimiter = ' '
    elif 1:
        tests = ["""{'f': 2, 'p': 'I_Ycyp41ejGmnASG8J8Gs_v4pdaafAdjjS2TpeWRLSYdD9t4q1o4879-O_7CrHrx6BSrNzsbzZaMdUHQkzNHCtNIKwMeywBKltlXaI_aZfQVWqi7bt4O2vhqqmo3Iy5LXJ8S0Sdqja3j7d84xbat0G3nPxntDxlJyO-SYf44grA', 't': 'A', 'i': -1, 'c': '#BF1260'}"""]
        delimiter = ' '

    results = []
    for line in tests:
        results.append(parse_line(line,delimiter))

    for idx,result in enumerate(results):
        print ()
        print ('LINE:',tests[idx])
        print ('ARGS:',len(result), type(result[0]))
        pp.pprint(result)