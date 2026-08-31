import xml.etree.ElementTree as ET
from pysat.solvers import Solver


FILE = "circuit.circ"


# ============================================================
# PARSE XML
# ============================================================

tree = ET.parse(FILE)
root = tree.getroot()
circuit = root.find(".//circuit")
comps = circuit.findall("comp")


def get_loc(comp):
    x, y = comp.get("loc").strip("()").split(",")
    return int(x), int(y)


def get_attr(comp, name):
    a = comp.find(f"a[@name='{name}']")
    return a.get("val") if a is not None else None


# ============================================================
# COLLECT TUNNELS
# ============================================================

# (x,y) -> [label1, label2, ...]
tunnels = {}

# Semua label tunnel
tunnel_labels = set()

for comp in comps:

    if comp.get("name") != "Tunnel":
        continue

    loc = get_loc(comp)
    label = get_attr(comp, "label")

    tunnels.setdefault(loc, []).append(label)
    tunnel_labels.add(label)


# ============================================================
# CHECK INPUT / OUTPUT
# ============================================================

print("[+] Checking pins...")

for i in range(200):
    name = f"b{i}"

    if name not in tunnel_labels:
        raise RuntimeError(
            f"Input {name} tidak ditemukan!"
        )

if "ONE" not in tunnel_labels:
    raise RuntimeError("ONE tidak ditemukan!")

if "OK" not in tunnel_labels:
    raise RuntimeError("OK tidak ditemukan!")

print("[+] b0..b199 OK")
print("[+] ONE OK")
print("[+] OK output OK")


# ============================================================
# PARSE GATES
# ============================================================

gates = []

for comp in comps:

    name = comp.get("name")

    if name not in ("AND Gate", "XOR Gate"):
        continue

    x, y = get_loc(comp)

    if name == "AND Gate":
        dx = -30
        gate_type = "AND"

    else:
        dx = -40
        gate_type = "XOR"

    p1 = (x + dx, y - 10)
    p2 = (x + dx, y + 10)
    po = (x, y)

    if p1 not in tunnels:
        raise RuntimeError(
            f"Input 1 gate {name} di {(x,y)} tidak ditemukan"
        )

    if p2 not in tunnels:
        raise RuntimeError(
            f"Input 2 gate {name} di {(x,y)} tidak ditemukan"
        )

    if po not in tunnels:
        raise RuntimeError(
            f"Output gate {name} di {(x,y)} tidak ditemukan"
        )

    gates.append({
        "type": gate_type,
        "in1": tunnels[p1][0],
        "in2": tunnels[p2][0],
        "out": tunnels[po][0],
        "loc": (x, y),
    })


print()
print(f"[+] Gates : {len(gates)}")
print(
    f"    AND  : "
    f"{sum(g['type'] == 'AND' for g in gates)}"
)
print(
    f"    XOR  : "
    f"{sum(g['type'] == 'XOR' for g in gates)}"
)


# ============================================================
# CHECK GATE OUTPUT UNIQUE
# ============================================================

gate_by_output = {}

for g in gates:

    out = g["out"]

    if out in gate_by_output:
        raise RuntimeError(
            f"Net {out} mempunyai lebih dari satu driver!"
        )

    gate_by_output[out] = g


print("[+] Semua output gate unik")


# ============================================================
# OPTIONAL: PRINT ALL GATES
# ============================================================

# Uncomment kalau mau dump semua gate.
#
# for i, g in enumerate(gates):
#     print(
#         f"{i:04d}: "
#         f"{g['type']:3s} "
#         f"{g['in1']:8s} "
#         f"{g['in2']:8s} "
#         f"-> {g['out']}"
#     )


# ============================================================
# SAT VARIABLES
# ============================================================

all_nets = set()

for g in gates:
    all_nets.add(g["in1"])
    all_nets.add(g["in2"])
    all_nets.add(g["out"])

for i in range(200):
    all_nets.add(f"b{i}")

all_nets.add("ONE")
all_nets.add("OK")


var = {}
next_var = 1

for net in sorted(all_nets):
    var[net] = next_var
    next_var += 1


def V(net):
    return var[net]


# ============================================================
# CNF
# ============================================================

clauses = []


# ONE = 1
clauses.append([V("ONE")])


# ============================================================
# AND
#
# z = a & b
# ============================================================

def add_and(a, b, z):

    clauses.append([-a, -b, z])
    clauses.append([a, -z])
    clauses.append([b, -z])


# ============================================================
# XOR
#
# z = a ^ b
# ============================================================

def add_xor(a, b, z):

    clauses.append([a, b, -z])
    clauses.append([-a, -b, -z])
    clauses.append([a, -b, z])
    clauses.append([-a, b, z])


for g in gates:

    a = V(g["in1"])
    b = V(g["in2"])
    z = V(g["out"])

    if g["type"] == "AND":
        add_and(a, b, z)

    elif g["type"] == "XOR":
        add_xor(a, b, z)


# ============================================================
# REQUIRE OK = 1
# ============================================================

clauses.append([V("OK")])


# ============================================================
# SOLVE
# ============================================================

print()
print("[+] Solving SAT...")

with Solver(
    name="glucose3",
    bootstrap_with=clauses
) as solver:

    if not solver.solve():

        print("[-] NO SOLUTION")
        raise SystemExit(1)

    model = solver.get_model()


model_set = set(model)


# ============================================================
# EXTRACT b0..b199
# ============================================================

bits = []

for i in range(200):

    bit = 1 if V(f"b{i}") in model_set else 0

    bits.append(bit)


bit_string = "".join(str(x) for x in bits)


print()
print("=" * 70)
print("SAT RESULT")
print("=" * 70)

print("OK =", 1)

print()
print("200 BIT:")
print(bit_string)


# ============================================================
# MANUAL CIRCUIT EVALUATION
# ============================================================

input_values = {
    f"b{i}": bits[i]
    for i in range(200)
}


# Cache nilai yang sudah dihitung
memo = {
    "ONE": 1,
    **input_values
}


def eval_net(net, stack=None):

    # Sudah diketahui
    if net in memo:
        return memo[net]

    if stack is None:
        stack = set()

    # Deteksi loop
    if net in stack:
        raise RuntimeError(
            f"Combinational loop detected: {net}"
        )

    if net not in gate_by_output:
        raise RuntimeError(
            f"Tidak tahu sumber net: {net}"
        )

    stack.add(net)

    g = gate_by_output[net]

    a = eval_net(g["in1"], stack)
    b = eval_net(g["in2"], stack)

    if g["type"] == "AND":
        value = a & b

    elif g["type"] == "XOR":
        value = a ^ b

    else:
        raise RuntimeError(
            f"Unknown gate: {g['type']}"
        )

    stack.remove(net)

    memo[net] = value

    return value


manual_ok = eval_net("OK")


# ============================================================
# MANUAL CHECK
# ============================================================

print()
print("=" * 70)
print("MANUAL CHECK")
print("=" * 70)

print("OK =", manual_ok)

if manual_ok != 1:

    print()
    print("[-] ERROR!")
    print("    SAT mengatakan OK=1")
    print("    tetapi evaluasi manual mengatakan OK=0")

    raise SystemExit(1)

print("[+] OK = 1")
print("[+] SAT result cocok dengan manual evaluation")


# ============================================================
# ASCII DECODE
# ============================================================

def bits_to_bytes(bits):

    if len(bits) % 8 != 0:
        raise ValueError(
            "Jumlah bit bukan kelipatan 8"
        )

    result = []

    for i in range(0, len(bits), 8):

        byte = bits[i:i + 8]

        value = 0

        for bit in byte:
            value = (value << 1) | bit

        result.append(value)

    return bytes(result)


decoded = bits_to_bytes(bits)


# ============================================================
# FINAL OUTPUT
# ============================================================

print()
print("=" * 70)
print("DECODE")
print("=" * 70)

print("Bits :", len(bits))
print("Bytes:", len(decoded))

print()
print("HEX :")
print(decoded.hex())

print()
print("ASCII:")
print(repr(decoded.decode("ascii", errors="replace")))


# ============================================================
# PRINT EACH BYTE
# ============================================================

print()
print("BYTE TABLE:")

for i in range(0, len(bits), 8):

    b = bits[i:i + 8]

    value = 0

    for bit in b:
        value = (value << 1) | bit

    char = chr(value) if 32 <= value <= 126 else "."

    print(
        f"{i:03d}-{i+7:03d}  "
        f"{''.join(map(str,b))}  "
        f"0x{value:02x}  "
        f"{repr(char)}"
    )
