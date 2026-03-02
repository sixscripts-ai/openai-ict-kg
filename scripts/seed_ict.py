"""Purge Vex data and seed ICT concept nodes with embeddings."""
import sys, os
sys.path.insert(0, '/Users/villain/.gemini/antigravity/scratch/openai-ict-kg/src')
os.environ['DATABASE_URL'] = 'postgresql://postgres.ospatjmicmbjimznwnzi:Ict-kg-DB-2026!@aws-0-us-west-2.pooler.supabase.com:6543/postgres'

from ict_kg.db import Database
from ict_kg.embeddings import LocalDeterministicEmbedder, encode_embedding

db = Database()
embedder = LocalDeterministicEmbedder()
TENANT = 'default'

# Purge
with db.connection() as conn:
    cur = conn.cursor()
    cur.execute("DELETE FROM edges WHERE tenant_id = %s", (TENANT,))
    print("Purged", cur.rowcount, "edges")
    cur.execute("DELETE FROM nodes WHERE tenant_id = %s", (TENANT,))
    print("Purged", cur.rowcount, "nodes")

ICT = [
    ("Market Structure", "The framework of price action defined by swing highs and swing lows. Understanding market structure is the foundation of ICT methodology."),
    ("Break of Structure", "BOS - occurs when price breaks a previous swing high (bullish) or swing low (bearish), confirming continuation of the current trend."),
    ("Market Structure Shift", "MSS - a decisive break of a key swing point that signals a potential change in trend direction. Often accompanied by displacement."),
    ("Change of Character", "CHoCH - the first sign that the prevailing market structure may be changing. The earliest but less confirmed signal of reversal."),
    ("CISD", "Change in State of Delivery - a shift in how price is being delivered by the algorithm. CISD often confirms a structural break."),
    ("Liquidity", "Resting orders above swing highs (buyside) and below swing lows (sellside) that smart money targets for fills."),
    ("Buyside Liquidity", "Buy stops resting above swing highs, equal highs, and previous session highs. Targeted when smart money needs to sell."),
    ("Sellside Liquidity", "Sell stops resting below swing lows, equal lows, and previous session lows. Targeted when smart money needs to buy."),
    ("Liquidity Sweep", "When price runs through a liquidity level to trigger resting stop orders before reversing."),
    ("Equal Highs", "Two or more swing highs at the same price level. Build up buyside liquidity directly above them."),
    ("Equal Lows", "Two or more swing lows at the same price level. Build up sellside liquidity directly below them."),
    ("Imbalance", "Any area where price moved too aggressively, leaving gaps. These regions act as magnets for future price rebalancing."),
    ("Fair Value Gap", "FVG - a three-candle pattern where the wicks of candles 1 and 3 do not overlap, creating an inefficiency."),
    ("SIBI", "Sell-side Imbalance, Buyside Inefficiency - a bearish FVG formed during aggressive selling."),
    ("BISI", "Buy-side Imbalance, Sellside Inefficiency - a bullish FVG formed during aggressive buying."),
    ("Volume Imbalance", "The gap between one candle close and the next candle open. A two-candle pattern that often acts as support/resistance."),
    ("Consequent Encroachment", "CE - the 50% midpoint of a Fair Value Gap. Price often reacts precisely at the CE level."),
    ("Void", "A large gap in price action where no trades were executed. Extreme imbalances that act as strong magnets for price."),
    ("Order Block", "The last up-close candle before a bearish move or last down-close candle before a bullish move. Where institutional orders were placed."),
    ("Breaker Block", "A failed order block that gets violated and flips its role. Extremely reliable because they represent trapped traders."),
    ("Mitigation Block", "An old order block from a previous price leg that price returns to for mitigation before new directional movement."),
    ("Rejection Block", "Formed when price wicks aggressively into a zone and sharply rejects. Shows where smart money defended a level."),
    ("Propulsion Block", "A consolidation zone that launches price in one direction after building energy in a tight range."),
    ("Asia Session", "The Asian trading session (approx. 20:00-00:00 EST). Builds the initial range and establishes liquidity levels."),
    ("London Session", "The London trading session (approx. 02:00-05:00 EST). Typically sweeps Asia liquidity and sets the daily move."),
    ("New York Session", "The New York trading session. NY AM (07:00-10:00 EST) is where the most institutional volume occurs."),
    ("London Killzone", "The optimal trading window during the London session (02:00-05:00 EST). Highest institutional activity."),
    ("New York Killzone", "The optimal trading window during the New York session (07:00-10:00 EST)."),
    ("Silver Bullet", "ICT 10:00-11:00 EST trading window. High-probability FVG entry after initial morning volatility."),
    ("New York AM", "The morning portion of the New York session (07:00-10:00 EST). Highest-probability ICT setups."),
    ("New York PM", "The afternoon portion of the New York session (13:30-16:00 EST). Often sees AM move reversals."),
    ("Displacement", "A sharp, aggressive price move with large-bodied candles that breaks structure and creates FVGs. Footprint of institutional order flow."),
    ("Judas Swing", "A false move at session start designed to trap retail traders before reversing in the true direction."),
    ("Stop Hunt", "When the algorithm drives price to where retail stop losses are clustered, triggering them for institutional liquidity."),
    ("Liquidity Grab", "A quick aggressive move beyond a key level to capture resting orders before sharply reversing."),
    ("Premium Zone", "The upper half of a price range, above equilibrium (50%). Sell/short in premium for high-probability trades."),
    ("Discount Zone", "The lower half of a price range, below equilibrium (50%). Buy/go long in discount for high-probability trades."),
    ("Equilibrium", "The 50% level of any defined price range. Divides premium from discount."),
    ("Price Action", "The study of raw price movement without indicators. ICT methodology is entirely based on price action."),
    ("Higher Timeframe", "HTF - the larger timeframe for directional bias (Monthly, Weekly, Daily, 4H). Top-down analysis starts here."),
    ("Lower Timeframe", "LTF - the smaller timeframe for precise entries (15m, 5m, 1m). Used after establishing HTF bias."),
    ("Power of 3", "ICT daily price delivery: Accumulation then Manipulation then Distribution."),
    ("Optimal Trade Entry", "OTE - the 62-79% Fibonacci retracement zone of a displacement leg. Best entries in HTF OB or FVG."),
    ("Turtle Soup", "ICT setup where price sweeps an old high/low and reverses. Uses Turtle Trading breakout levels as liquidity targets."),
    ("Trend Change", "A confirmed reversal validated by an MSS. Requires liquidity sweep plus displacement in new direction."),
    ("Structure Break", "When price violates a key swing point, breaking the HH/HL or LH/LL chain."),
    ("Price Level", "Any significant horizontal level the algorithm references - session highs/lows, OB boundaries, FVG extremes."),
]

print("Seeding", len(ICT), "ICT concepts with embeddings...")
with db.connection() as conn:
    cur = conn.cursor()
    for title, content in ICT:
        text = title + " " + content
        emb = embedder.embed(text)
        emb_str = encode_embedding(emb)
        cur.execute(
            "INSERT INTO nodes (tenant_id, title, content, domain, embedding_model, metadata, embedding) "
            "VALUES (%s, %s, %s, %s, %s, '{}'::jsonb, %s) RETURNING id",
            (TENANT, title, content, 'ict', embedder.name, emb_str)
        )
        nid = cur.fetchone()[0]
        print("  +", nid, title)
print("Seeded", len(ICT), "concepts.\n")

# Wire edges
print("Running auto_wire_edges...")
from ict_kg.wiring import auto_wire_edges
counts = auto_wire_edges(db, tenant_id=TENANT)
print("  semantic:", counts.get('semantic', 0))
print("  domain:", counts.get('domain', 0))
print("  ontology:", counts.get('ontology', 0))
print("  TOTAL:", sum(counts.values()))
print("\nDone!")
