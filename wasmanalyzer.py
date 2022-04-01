#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Usage:
# python3 wasmanalyzer.py -d -f nic_testbench/wasmwat_samples/cryptonight/cryptonight.wasm 
import argparse, sys, os, json
from operator import mod
from graphviz import Digraph, render
import hashlib
import vt
import subprocess
from classes import classes
from wasm import (
    decode_module, decode_bytecode,
    format_instruction, format_lang_type, 
    format_mutability, format_function,
    SEC_DATA, SEC_ELEMENT, SEC_GLOBAL,
    SEC_CODE, SEC_TYPE, SEC_FUNCTION, Section,
    INSN_ENTER_BLOCK,
    INSN_LEAVE_BLOCK,)

from logging import getLogger
logging = getLogger(__name__)

#Retrieve sha256 of file
def get_hash(file) -> hex:
    sha256_hash = hashlib.sha256()
    with open(file,"rb") as f:
        for block in iter(lambda: f.read(65536),b""):
            sha256_hash.update(block)
        
        return sha256_hash.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Malwasm - WebAssembly Scanner for potential malware')

    inputs = parser.add_argument_group('IO arguments')
    inputs.add_argument('-f', '--file', required=True,
                        help='binary file (.wasm)')
    
    inputs.add_argument('-r', '--rule',
                        help='rule file (.json)')

    inputs.add_argument('-fn', '--func',
                        help='function name for CFG & DFG')     

    features = parser.add_argument_group('Features')
    features.add_argument('-d', '--disassmble',
                        action='store_true', 
                        help='disassmble .wasm to wat-like format')

    # features.add_argument('-a', '--analyse',
    #                       action='store_true',
    #                       help='print Functions instructions analytics')

    features.add_argument('-a', '--analyse', nargs='?', default='default', const='1',
                          help='[ANALYSE] : 1 - surface, 2 - deep | -a [1,2] -f <wasm> module against -r <rule.json>')
                        
    features.add_argument('-gr', '--genRule',
                          action='store_true',
                          help='generate JSON rule')
                        
    features.add_argument('-vt', '--vt-api-key',
                          action='store_true',
                          help='enter virustotal API key')
    
    features.add_argument('-cg', '--gen-callgraph',
                          action='store_true',
                          help='generate callgraph')
    
    features.add_argument('-cfg', '--gen-control-flow-graph',
                            action='store_true',
                          help='generate control-flow-graph with specified function name')
    
    features.add_argument('-dfg', '--gen-data-flow-graph',
                            action='store_true',    
                          help='generate data-flow-graph with specified function name')

    args = parser.parse_args()

    # Global Variables
    mod_obj = classes.Module() # Module Object for -d, -a, -gr
    rule_obj = classes.Rule() # Rule Object for -r
    an_obj = classes.Analysis() # Analysis Object for -a
    
    # Process input code
    if args.file:
        # Read file
        with open(args.file, 'rb') as raw:
            raw_read = raw.read()
            raw.close()
            
        mod_iter = iter(decode_module(raw_read, decode_name_subsections=True))
        
        # Disassemble OR Generate JSON Rule
        if args.genRule or args.disassmble:
            mod_obj.disassemble(mod_iter) # disassemble    
            mod_obj.profile_module()
            mod_obj.analyse_cfg()

            # Export disassemble results
            mod_obj.export_dis_txt(args.file) # Write out Module information
            mod_obj.export_dis_wat(args.file) # Write out Module pseudo wat

            # Save json rule
            if args.genRule:
                mod_obj.export_rule_json(args.file)

        # Analyse .wasm against JSON
        if args.analyse:
            analyse_level = int(args.analyse) if args.analyse == '1' or '2' else 1
            if not args.rule: # Temp check, need to fix in argparse
                print('specify json rule with -r <filename.json>')
                return

            # Load rule in Rule obj
            with open(args.rule) as rule_raw:
                rule_json = json.load(rule_raw)
                rule_obj.load_json(rule_json)

            # Disassemble wasm -> profile -> analyse CFG
            mod_obj.disassemble(mod_iter) # disassemble    
            mod_obj.profile_module()
            mod_obj.analyse_cfg()

            an_obj.analyse(mod_obj, rule_obj, analyse_level) # Conduct analysis
            an_obj.export_results(args.file)

        # Implement CG function
        if args.gen_callgraph:
        # Method 1
        #     graph = Digraph(filename='wasm_cfg',format='svg')
        #     for d in mod_obj.called_by:
        #         graph.node(d, d)
        #         print(len(mod_obj.called_by[d]))
        #         if len(mod_obj.called_by[d]) != 0:
        #             for i in mod_obj.called_by[d]:
        #                 print(i)
        #                 graph.edge(d, i)    
        #     graph.render(directory='Output')
        # Method 2
            subprocess.Popen(["./resources/executables/wasp.exe", "callgraph", args.file, "-o","output/graph.dot"], 
                                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT).wait()
            render('dot', 'svg', "output/graph.dot")

        # Implement CFG function
        if args.gen_control_flow_graph:
            if args.func:
                subprocess.Popen(["./resources/executables/wasp.exe", "cfg", "-f", args.func, args.file, "-o","output/{}_cfg.dot".format(args.func)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT).wait()
                render('dot', 'svg', "output/{}_cfg.dot".format(args.func))
            else: 
                logging.error('specify function name with the parameter -func <func_name>')
                sys.exit(1)
        
        # Implement DFG function
        if args.gen_data_flow_graph:
            if args.func:
                subprocess.Popen(["./resources/executables/wasp.exe", "dfg", "-f", args.func, args.file, "-o","output/{}_dfg.dot".format(args.func)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT).wait()
                render('dot', 'svg', "output/{}_dfg.dot".format(args.func))
            else: 
                logging.error('specify function name with the parameter -func <func_name>')
                sys.exit(1)

        #Virustotal Function
        if args.vt_api_key:
            client = vt.Client(args.vt_api_key)
            with open(args.file, "rb") as f:
                try:
                    analysis = client.scan_file(f, wait_for_completion=True)
                    assert analysis.status == "completed"
                    report = client.get_json(f"/files/{get_hash(args.file)}")
                except vt.error.APIError as e:
                    print("Virustotal encounters an error code: {} with error message: {}".format(e.code, e.message))
                    client.close()
                    sys.exit(1)
            
            print(report["data"]["attributes"]["last_analysis_stats"]["malicious"])
            client.close()
    

if __name__ == '__main__':
    main()
