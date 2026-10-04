from pathlib import Path
p=Path("index.html")
s=p.read_text(encoding="utf-8")
old='const removes=["SORTIE","VENTE","CORRECTION_MOINS","RETRAIT_STOCK","FRAIS_MEDICAUX"].includes(type);'
new='const removes=["SORTIE","VENTE","CORRECTION_MOINS","RETRAIT_STOCK"].includes(type);'
if s.count(old)!=1:
    raise SystemExit(f"expected one removes line, found {s.count(old)}")
s=s.replace(old,new,1)
# Explicitly keep FRAIS_MEDICAUX quantity_delta and cash_delta at zero.
old2='const qDelta=["ACHAT","DEPOT","CORRECTION_PLUS"].includes(type)?qty:removes?-qty:0;'
new2='const qDelta=type==="FRAIS_MEDICAUX"?0:(["ACHAT","DEPOT","CORRECTION_PLUS"].includes(type)?qty:removes?-qty:0);'
if s.count(old2)!=1:
    raise SystemExit(f"expected one qDelta line, found {s.count(old2)}")
s=s.replace(old2,new2,1)
old3='const cashDelta=type==="ACHAT"?-total:type==="VENTE"?total:0;'
new3='const cashDelta=type==="FRAIS_MEDICAUX"?0:(type==="ACHAT"?-total:type==="VENTE"?total:0);'
if s.count(old3)!=1:
    raise SystemExit(f"expected one cashDelta line, found {s.count(old3)}")
s=s.replace(old3,new3,1)
p.write_text(s,encoding="utf-8")
