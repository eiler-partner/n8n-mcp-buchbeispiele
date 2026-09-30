"""Synthetic CSV cases; no customer or provider data."""

CLEAN = (
    "order_id,region,amount_cents,customer\n"
    'O-1,north,1200,"Aster, GmbH"\n'
    "O-2,south,500,Birke\n"
    "O-3,north,0,Cedar\n"
)

DIRTY = (
    "order_id,region,amount_cents,customer\n"
    "O-4,north,1200,Dahlie\n"
    "O-5,south,abc,Eiche\n"
    "O-4,north,300,Dahlie\n"
    "O-6,south,-1,Fichte\n"
)

CASES = {"clean": CLEAN, "dirty": DIRTY}
