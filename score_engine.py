"""
Python port of the scoring engine in the web dashboard (nse-stock-screener.html).
Keep the two in sync if you change scoring bands in one place.
"""
from dataclasses import dataclass, field


def _round1(x):
    return round(x, 1) if x is not None else None


def business_quality_score(f: dict) -> float:
    roce_p = 0 if f["roce"] < 8 else 1 if f["roce"] < 12 else 2 if f["roce"] < 18 else 3 if f["roce"] < 25 else 4
    roe_p = 0 if f["roe"] < 10 else 1 if f["roe"] < 15 else 2 if f["roe"] < 20 else 3
    m = f["marginChgBps"]
    margin_p = 3 if m > 150 else 2 if m > 0 else 1 if m > -100 else 0
    rev_cons_p = 2 if (f["revCagr3"] > 10 and f["revCagr5"] > 10) else 1 if (f["revCagr3"] > 0 and f["revCagr5"] > 0) else 0
    eps_cons_p = 2 if (f["epsCagr3"] > 10 and f["epsCagr5"] > 10) else 1 if (f["epsCagr3"] > 0 and f["epsCagr5"] > 0) else 0
    cfo_pat = f["cfo"] / f["pat"] if f["pat"] else 0
    fcf_pat = f["fcf"] / f["pat"] if f["pat"] else 0
    fcf_gen_p = 3 if (cfo_pat > 0.8 and fcf_pat > 0.6 and f["fcf"] > 0) else 2 if (cfo_pat > 0.5 and f["fcf"] > 0) else 1 if f["fcf"] > 0 else 0
    debt_q_p = 2 if (f["de"] < 0.5 and f["intCov"] > 6) else 1 if (f["de"] < 1 and f["intCov"] > 3) else 0
    promo_q = 1 if (f["promoterHold"] >= 40 and f["promoterPledge"] == 0) else 0.5 if (f["promoterHold"] >= 40 and f["promoterPledge"] < 5) else 0
    total = roce_p + roe_p + margin_p + rev_cons_p + eps_cons_p + fcf_gen_p + debt_q_p + promo_q
    return _round1(total / 20 * 100)


def growth_score(f: dict) -> float:
    rev_g = 0 if f["revCagr3"] < 5 else 1 if f["revCagr3"] < 10 else 2 if f["revCagr3"] < 15 else 3 if f["revCagr3"] < 20 else 4
    eps_g = 0 if f["epsCagr3"] < 5 else 1 if f["epsCagr3"] < 12 else 2 if f["epsCagr3"] < 20 else 3 if f["epsCagr3"] < 30 else 4
    m = f["marginChgBps"]
    marg_exp = 0 if m < 0 else 1 if m < 50 else 2 if m < 150 else 3 if m < 300 else 4
    qoq_g = 0 if f["qoqRev"] < 0 else 1 if f["qoqRev"] < 5 else 2 if f["qoqRev"] < 10 else 3 if f["qoqRev"] < 15 else 4
    return _round1((rev_g + eps_g + marg_exp + qoq_g) / 16 * 100)


def balance_sheet_score(f: dict) -> float:
    de_p = 4 if f["de"] < 0.3 else 3 if f["de"] < 0.6 else 2 if f["de"] < 1 else 1 if f["de"] < 1.5 else 0
    ic_p = 4 if f["intCov"] > 10 else 3 if f["intCov"] > 6 else 2 if f["intCov"] > 3 else 1 if f["intCov"] > 1.5 else 0
    cr_p = 4 if f["currentRatio"] > 2 else 3 if f["currentRatio"] > 1.5 else 2 if f["currentRatio"] > 1.2 else 1 if f["currentRatio"] > 1 else 0
    return _round1((de_p + ic_p + cr_p) / 12 * 100)


def cash_flow_score(f: dict) -> float:
    cfo_pat = f["cfo"] / f["pat"] if f["pat"] else 0
    fcf_pat = f["fcf"] / f["pat"] if f["pat"] else 0
    cfo_p = 4 if cfo_pat > 1 else 3 if cfo_pat > 0.8 else 2 if cfo_pat > 0.5 else 1 if cfo_pat > 0.2 else 0
    fcf_p = 4 if fcf_pat > 0.8 else 3 if fcf_pat > 0.5 else 2 if fcf_pat > 0.2 else 1 if fcf_pat > 0 else 0
    return _round1((cfo_p + fcf_p) / 8 * 100)


def valuation_score(v: dict):
    if not v.get("pe") or not v.get("medianPE") or not v.get("sectorPE"):
        return None
    hist_prem = (v["pe"] / v["medianPE"] - 1) * 100
    sec_prem = (v["pe"] / v["sectorPE"] - 1) * 100
    hist_p = 4 if hist_prem < -20 else 3 if hist_prem < 0 else 2 if hist_prem < 20 else 1 if hist_prem < 50 else 0
    sec_p = 4 if sec_prem < -20 else 3 if sec_prem < 0 else 2 if sec_prem < 20 else 1 if sec_prem < 50 else 0
    peg_p = 4 if v["peg"] < 1 else 3 if v["peg"] < 1.5 else 2 if v["peg"] < 2 else 1 if v["peg"] < 3 else 0
    fcfy_p = 4 if v["fcfYield"] > 6 else 3 if v["fcfYield"] > 4 else 2 if v["fcfYield"] > 2 else 1 if v["fcfYield"] > 0 else 0
    return _round1((hist_p + sec_p + peg_p + fcfy_p) / 16 * 100)


def technical_setup_score(t: dict) -> float:
    rsi = t["rsi"]
    rsi_p = 4 if 45 <= rsi <= 65 else 2 if 65 < rsi <= 75 else 2 if 35 <= rsi < 45 else 1 if rsi > 75 else 1 if rsi < 35 else 0
    macd_p = 4 if t["macd"] > 0 else 2 if t["macd"] > -1 else 0
    adx_p = 4 if t["adx"] > 25 else 3 if t["adx"] > 20 else 2 if t["adx"] > 15 else 1 if t["adx"] > 10 else 0
    brk_p = 4 if t["breakout"] else 0
    return _round1((rsi_p + macd_p + adx_p + brk_p) / 16 * 100)


def _rel_strength(t: dict, nifty12: float) -> float:
    return t["ret12m"] - nifty12


def momentum_score(t: dict, nifty12: float) -> float:
    rs12 = _rel_strength(t, nifty12)
    ret12_p = 4 if t["ret12m"] > 40 else 3 if t["ret12m"] > 25 else 2 if t["ret12m"] > 10 else 1 if t["ret12m"] > 0 else 0
    ret6_p = 4 if t["ret6m"] > 25 else 3 if t["ret6m"] > 15 else 2 if t["ret6m"] > 5 else 1 if t["ret6m"] > 0 else 0
    ma_p = (4 if (t["cmp"] > t["dma20"] > t["dma50"] > t["dma100"] > t["dma200"])
            else 2 if (t["cmp"] > t["dma20"] and t["cmp"] > t["dma200"])
            else 1 if t["cmp"] > t["dma200"] else 0)
    rs_p = 4 if rs12 > 25 else 3 if rs12 > 15 else 2 if rs12 > 5 else 1 if rs12 > 0 else 0
    return _round1((ret12_p + ret6_p + ma_p + rs_p) / 16 * 100)


def relative_strength_score(t: dict, nifty12: float) -> float:
    rs12 = _rel_strength(t, nifty12)
    return 100 if rs12 > 30 else 85 if rs12 > 20 else 70 if rs12 > 10 else 55 if rs12 > 0 else 35 if rs12 > -10 else 15


def volume_score(t: dict) -> float:
    ratio = t["vol"] / t["avgVol"] if t.get("avgVol") else 0
    return 100 if ratio > 2 else 80 if ratio > 1.5 else 60 if ratio > 1.2 else 40 if ratio > 1 else 20


def volatility_risk_score(t: dict, r: dict) -> float:
    atr_pct = (t["atr"] / t["cmp"] * 100) if t.get("cmp") else 0
    atr_p = 4 if atr_pct < 2 else 3 if atr_pct < 3 else 2 if atr_pct < 5 else 1 if atr_pct < 7 else 0
    beta = r.get("beta") or 1
    beta_p = 4 if beta < 0.8 else 3 if beta < 1 else 2 if beta < 1.3 else 1 if beta < 1.6 else 0
    dd3y = r["dd3y"]
    dd_p = 4 if dd3y > -15 else 3 if dd3y > -25 else 2 if dd3y > -40 else 1 if dd3y > -55 else 0
    vol_score = _round1((atr_p + beta_p + dd_p) / 12 * 100)
    advt = r["advt"]
    liq_score = 100 if advt > 50 else 80 if advt > 20 else 60 if advt > 10 else 40 if advt > 5 else 20
    return _round1((vol_score + liq_score) / 2)


def catalyst_score(catalysts: list):
    impact_num = {"High": 3, "Medium": 2, "Low": 1}
    priced_factor = {"No": 1, "Partial": 0.6, "Yes": 0.2}
    subs = []
    for c in catalysts or []:
        if c.get("desc") and c.get("prob") not in (None, ""):
            subs.append(float(c["prob"]) * (impact_num[c["impact"]] / 3) * priced_factor[c["pricedIn"]])
    if not subs:
        return None
    return _round1(sum(subs) / len(subs))


def red_flag_penalty(f: dict, flags: dict) -> int:
    pen = 0
    if f["promoterPledge"] > 0:
        pen -= 10
    if f["pat"] and (f["cfo"] / f["pat"]) < 0.5:
        pen -= 8
    if f["marginChgBps"] < -200:
        pen -= 7
    if flags.get("debtRising"):
        pen -= 8
    if flags.get("acctIrreg"):
        pen -= 15
    if flags.get("majorDilution"):
        pen -= 8
    if flags.get("insiderSelling"):
        pen -= 5
    if flags.get("relatedParty"):
        pen -= 10
    if flags.get("govConcern"):
        pen -= 15
    return pen


CLASS_BANDS = [(0, "Avoid"), (60, "Weak"), (70, "Watchlist"), (80, "Strong"), (90, "Exceptional")]
RR_BANDS = [(0, "Avoid"), (1.0, "Weak"), (1.5, "Acceptable"), (2.0, "Strong"), (3.0, "Exceptional")]


def classify(score, bands):
    if score is None:
        return "-"
    label = bands[0][1]
    for lo, name in bands:
        if score >= lo:
            label = name
    return label


DEFAULT_INV_WEIGHTS = {"quality": 25, "growth": 20, "valuation": 20, "balanceSheet": 15, "cashFlow": 10, "catalyst": 5, "momentum": 5}
DEFAULT_TRADE_WEIGHTS = {"momentum": 25, "relStrength": 20, "techSetup": 20, "volume": 15, "catalyst": 10, "volRisk": 10}


def compute_all(stock: dict, nifty12: float, capital: float, risk_pct: float,
                 inv_weights: dict = None, trade_weights: dict = None) -> dict:
    inv_weights = inv_weights or DEFAULT_INV_WEIGHTS
    trade_weights = trade_weights or DEFAULT_TRADE_WEIGHTS
    f, v, t, r = stock["fundamentals"], stock["valuation"], stock["technicals"], stock["risk"]

    bq, gr = business_quality_score(f), growth_score(f)
    bs, cf = balance_sheet_score(f), cash_flow_score(f)
    val = valuation_score(v)
    ts = technical_setup_score(t)
    mo = momentum_score(t, nifty12)
    rs = relative_strength_score(t, nifty12)
    vo = volume_score(t)
    vr = volatility_risk_score(t, r)
    cat = catalyst_score(stock.get("catalysts"))
    pen = red_flag_penalty(f, stock.get("flags", {}))

    nz = lambda x: 0 if x is None else x
    inv_raw = (nz(bq) * inv_weights["quality"] + nz(gr) * inv_weights["growth"] + nz(val) * inv_weights["valuation"]
               + nz(bs) * inv_weights["balanceSheet"] + nz(cf) * inv_weights["cashFlow"]
               + nz(cat) * inv_weights["catalyst"] + nz(mo) * inv_weights["momentum"]) / 100
    inv_final = max(0, inv_raw + pen)

    trade_raw = (nz(mo) * trade_weights["momentum"] + nz(rs) * trade_weights["relStrength"]
                 + nz(ts) * trade_weights["techSetup"] + nz(vo) * trade_weights["volume"]
                 + nz(cat) * trade_weights["catalyst"] + nz(vr) * trade_weights["volRisk"]) / 100
    trade_final = max(0, trade_raw + pen)

    h = stock.get("hypothesis", {})
    exp_return = exp_downside = reward_risk = None
    if h.get("bullProb") not in (None, "") and h.get("baseProb") not in (None, "") and h.get("bearProb") not in (None, ""):
        exp_return = _round1((float(h["bullProb"]) * float(h["bullRet"]) + float(h["baseProb"]) * float(h["baseRet"])
                               + float(h["bearProb"]) * float(h["bearRet"])) / 100)
        exp_downside = float(h["bearRet"])
        if exp_downside < 0:
            reward_risk = _round1(exp_return / abs(exp_downside))

    buy_zone_low = _round1(t["dma20"] * 0.98) if t.get("dma20") else None
    buy_zone_high = _round1(t["dma20"] * 1.02) if t.get("dma20") else None
    stop = _round1(t["cmp"] - 1.5 * t["atr"]) if t.get("cmp") and t.get("atr") else None
    pos_size = None
    if stop is not None and t.get("cmp") and (t["cmp"] - stop) > 0:
        pos_size = int((capital * risk_pct / 100) / (t["cmp"] - stop))

    inv_class = classify(inv_final, CLASS_BANDS)
    trade_class = classify(trade_final, CLASS_BANDS)
    rr_class = classify(reward_risk, RR_BANDS) if reward_risk is not None else "-"

    action = "AVOID"
    if h.get("status") == "Invalid":
        action = "AVOID (Hypothesis Invalid)"
    elif pen <= -15:
        action = "AVOID (Red Flags)"
    elif inv_final >= 80 and trade_final >= 70 and reward_risk is not None and reward_risk >= 2:
        action = "BUY"
    elif inv_final >= 80 and trade_final < 70:
        action = "BUY ON PULLBACK"
    elif inv_final >= 70:
        action = "WATCHLIST"

    return {
        "businessQuality": bq, "growth": gr, "balanceSheet": bs, "cashFlow": cf, "valuation": val,
        "technicalSetup": ts, "momentum": mo, "relativeStrength": rs, "volume": vo, "volatilityRisk": vr,
        "catalyst": cat, "redFlagPenalty": pen,
        "investmentScoreRaw": _round1(inv_raw), "investmentScoreFinal": _round1(inv_final), "investmentClass": inv_class,
        "tradingScoreRaw": _round1(trade_raw), "tradingScoreFinal": _round1(trade_final), "tradingClass": trade_class,
        "expectedReturn": exp_return, "expectedDownside": exp_downside, "rewardRisk": reward_risk, "rewardRiskClass": rr_class,
        "buyZoneLow": buy_zone_low, "buyZoneHigh": buy_zone_high, "stop": stop, "positionSizeShares": pos_size,
        "action": action,
    }
