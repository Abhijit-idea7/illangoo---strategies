# strategies package  (S4 Channel Breakout dropped — consistently unprofitable)
from .s1_price_action        import S1PriceAction
from .s2_fib_retracement     import S2FibRetracement
from .s3_ema_crossover       import S3EMACrossover
from .s5_jnsar               import S5JNSAR
from .s6_retracement_reentry import S6RetracementReentry
from .s9_divergence          import S9Divergence

ALL_STRATEGIES = {
    "S1": S1PriceAction,
    "S2": S2FibRetracement,
    "S3": S3EMACrossover,
    "S5": S5JNSAR,
    "S6": S6RetracementReentry,
    "S9": S9Divergence,
}
