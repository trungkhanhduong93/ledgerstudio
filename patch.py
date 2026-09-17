import os

file_path = r'd:\IACC HCM\iPOS ACC\ACC PMKT\LedgerReport\index.html'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the injection point
start_idx = -1
for i, line in enumerate(lines):
    if 'arr.splice(i, 0, col);' in line:
        start_idx = i + 1
        break

if start_idx != -1:
    missing_code = '''                                                        setGroupByLedger(arr);
                                                    }
                                                }
                                            }}
                                            className="bg-white border border-indigo-200 text-indigo-700 px-3 py-1.5 rounded-full text-[10px] font-black flex items-center gap-2 shadow-sm animate-fade-in cursor-move">
                                            {g}
                                            <button onClick={() => setGroupByLedger(groupByLedger.filter(x => x !== g))} className="text-slate-300 hover:text-red-500 transition-colors bg-slate-50 hover:bg-red-50 rounded-full w-4 h-4 flex items-center justify-center"><Icon name="lock" size={8}/></button>
                                        </div>
                                    ))}
                                </div>
                                <div className="flex-1 min-h-0 bg-white border border-slate-200 rounded-2xl shadow-2xl overflow-hidden flex flex-col mx-0">
                                    <div className="flex-1 min-h-0 overflow-auto custom-scrollbar" ref={ledgerScrollRef}>
'''
    # Check if we already injected it
    if 'setGroupByLedger(arr);' not in lines[start_idx]:
        lines.insert(start_idx, missing_code)

# Now remove the DEBIT_CREDIT header line
new_lines = []
for line in lines:
    if 'field="DEBIT_CREDIT"' in line and 'Ph' in line and 'sinh' in line:
        pass # skip it
    else:
        new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Done")
