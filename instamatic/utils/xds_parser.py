import sys
from pathlib import Path
import os
import time
from math import radians, cos
import shutil


def volume(cell):
    """Returns volume for the general case from cell parameters"""
    a, b, c, al, be, ga = cell
    al = radians(al)
    be = radians(be)
    ga = radians(ga)
    vol = a*b*c * \
        ((1+2*cos(al)*cos(be)*cos(ga)-cos(al)**2-cos(be)**2-cos(ga)**2)
         ** .5)
    return vol


class xds_parser(object):
    """docstring for xds_parser"""
    def __init__(self, filename):
        super(xds_parser, self).__init__()
        self.ios_threshold = 0.8
        
        self.filename = Path(filename).resolve()
        self.d = self.parse()

    def parse(self):
        ios_threshold = self.ios_threshold

        fn = self.filename
    
        f = open(fn, "r")
    
        in_block = False
        block = []
    
        d = {}
    
        for line in f:
            if line.startswith(" SUBSET OF INTENSITY DATA WITH SIGNAL/NOISE >= -3.0 AS FUNCTION OF RESOLUTION"):
                in_block = True
                block = []
            elif line.startswith("    total"):
                block.append(line.strip("\n"))
                in_block = False
            elif line.startswith(" UNIT CELL PARAMETERS"):
                cell = list(map(float, line.strip("\n").split()[3:9]))
            elif line.startswith(" SPACE GROUP NUMBER"):
                spgr = int(line.strip("\n").split()[-1])
            elif line.startswith("     a        b          ISa"):
                line = next(f)
                inp = line.split()
                ISa = float(inp[2])
            elif line.startswith("   WILSON LINE (using all data)"):
                inp = line.split()
                Boverall = float(inp[-3])
            elif line.startswith("   --------------------------------------------------------------------------"):
                line = next(f)
                inp = line.split()
                resolution_range = float(inp[0]), float(inp[1])
    
            if in_block:
                if line:
                    block.append(line.strip("\n"))
    
        vol = volume(cell)
    
        d["ISa"] = ISa
        d["Boverall"] = Boverall
    
        dmin = 999
    
        for line in block:
            inp = line.split()
            if len(inp) != 14:
                continue
    
            try:
                res = float(inp[0])
            except ValueError:
                res = inp[0]
                if res != "total":
                    continue
    
            res = float(inp[0]) if inp[0] != "total" else inp[0]
            ntot, nuniq, completeness = int(inp[1]), int(inp[2]), float(inp[4].strip("%"))
            ios, rmeas, cchalf = float(inp[8]), float(inp[9].strip("%")), float(inp[10].strip("*"))
    
            if ios < ios_threshold and res != "total":
                continue
    
            if (res != "total") and (res < dmin):
                shell = (dmin, res)
                dmin = res
    
            d[res] = {"ntot": ntot, "nuniq": nuniq, "completeness": completeness, "ios": ios, "rmeas": rmeas, "cchalf": cchalf}
    
        if dmin == 999:
            return
    
        d["outer"] = dmin
        d["outer_shell"] = shell
        d["res_range"] = resolution_range
        d["volume"] = vol
        d["cell"] = cell
        d["spgr"] = spgr
        d["fn"] = fn
    
        return d

    def print_info_header(self):
        print("  #   dmax  dmin    ntot   nuniq   compl   i/sig   rmeas CC(1/2)     ISa   B(ov)")
        print("-------------------------------------------------------------------------")

    def print_filename(self):
        print("#", self.filename)

    def print_cell(self, sequence=0):
        d = self.d
        i = sequence
        fn = self.filename
        print(f"{i: 3d}: {fn.parents[0]} # {time.ctime(os.path.getmtime(fn))}")
        print("Spgr {: 4d} - Cell {:10.2f}{:10.2f}{:10.2f}{:10.2f}{:10.2f}{:10.2f} - Vol {:10.2f}".format(d["spgr"], *d["cell"], d["volume"]))

    def print_info(self, sequence=0, outer_shell=True, filename=False):
        d = self.d
        k = sequence
        if k == 0:
            self.print_info_header()
        
        dmax, dmin = d["res_range"]

        if filename:
            end = f"  # {d['fn']}\n"
        else:
            end = "\n"

        print("{k: 3d} {dmax: 6.2f}{dmin: 6.2f}{ntot: 8d}{nuniq: 8d}{completeness: 8.1f}{ios: 8.2f}{rmeas: 8.1f}{cchalf: 8.1f}{ISa: 8.2f}{Boverall: 8.2f}".format(
        k=k, dmax=dmax, dmin=dmin, **d["total"], **d), end=end)

        if outer_shell:
            outer = d["outer"]
            dmax_sh, dmin_sh = d["outer_shell"]
            print("  - {dmax: 6.2f}{dmin: 6.2f}{ntot: 8d}{nuniq: 8d}{completeness: 8.1f}{ios: 8.2f}{rmeas: 8.1f}{cchalf: 8.1f}".format(
                k=k, dmax=dmax_sh, dmin=dmin_sh, **d[outer]))

    @property
    def volume(self):
        return self.d["volume"]

    @property
    def unit_cell(self):
        return self.d["cell"]

    @property
    def space_group(self):
        return self.d["spgr"]

    def cell_as_dict(self):
        d = dict(zip("a b c al be ga".split(), self.unit_cell))
        d["volume"] = self.volume
        d["spgr"] = self.space_group
        return d


def cells_to_excel(ps, out="cells.xlsx"):
    """Takes a list of `xds_parser` instances and writes the cell
    parameters to an excel file `cells.xlsx`.
    """
    d = {}
    for i, p in enumerate(ps):
        d[i] = p.cell_as_dict()

    import pandas as pd
    df = pd.DataFrame(d).T
    df = df["spgr a b c al be ga volume".split()]
    if not os.path.exists(out):
        df.to_excel(out)


def cells_to_cellparm(ps):
    """Takes a list of `xds_parser` instances and writes the cell
    parameters to an instruction file `CELLPARM.INP` for the program
    `cellparm`.
    """    
    # write cellparm input file
    with open("CELLPARM.INP", "w") as f:
        for i, p in enumerate(ps):
            fn = p.filename
            cell = p.unit_cell
            ntot = p.d["total"]["ntot"]
            print(f"! {i: 3d} from {fn}", file=f)
            print("UNIT_CELL_CONSTANTS= {:10.2f}{:10.2f}{:10.2f}{:10.2f}{:10.2f}{:10.2f} WEIGHT= {ntot}".format(*cell, ntot=ntot), file=f)


def gather_xds_ascii(ps):
    """Takes a list of `xds_parser` instances and gathers the 
    corresponding `XDS_ASCII.HKL` files into the current directory.
    The data source and numbering scheme is summarized in the file `filelist.txt`.
    """
    # gather xds_ascii and prepare filelist
    with open("filelist.txt", "w") as f:
        for i, p in enumerate(ps):
            fn = p.filename
            src = fn.with_name("XDS_ASCII.HKL")
            dst = f"{i:02d}_XDS_ASCII.HKL"
            shutil.copy(src, dst)
    
            dmax, dmin = p.d["res_range"]
            print(f" {i: 3d} {dst} {dmax:8.2f} {dmin:8.2f}  # {fn}", file=f)  


def parse_fns(fns):
    """Parse list of filenames"""
    new_fns = []
    for fn in fns:
        if fn.is_dir():
            new_fns.extend(list(fn.glob("**/CORRECT.LP")))
        else:  
            new_fns.append(fn)
    # new_fns = [fn for fn in new_fns if "reprocessed" in str(fn)]
    new_fns = [fn.resolve() for fn in new_fns]
    return new_fns


def main():
    fns = sys.argv[1:]
    
    if not fns:
        fns = [Path(".")]
    else:
        fns = [Path(fn) for fn in fns]
    
    fns = parse_fns(fns)
    print(f"Found {len(fns)} files matching CORRECT.LP\n")
    
    xdsall = [xds_parser(fn) for fn in fns]
    
    for i, p in enumerate(xdsall):
        p.print_cell(sequence=i)
    
    print()
    
    for i, p in enumerate(xdsall):
        p.print_info(sequence=i, filename=True)
    
    print()
    
    cells_to_excel(xdsall)
    cells_to_cellparm(xdsall)
    
    gather_xds_ascii(xdsall)


if __name__ == '__main__':
    main()
