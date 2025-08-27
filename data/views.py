import datetime
import requests
import concurrent.futures
from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta, time
from v1.models import AuthToken
from .models import OptionData, OIDifference
import pytz

ist = pytz.timezone("Asia/Kolkata")


def get_token():
    token_obj = AuthToken.objects.first()
    return token_obj.access_token if token_obj else None


# TOKEN = "eyJraWQiOiJaTUtjVXciLCJhbGciOiJFUzI1NiJ9.eyJleHAiOjE3NTYyNTQ2MDAsImlhdCI6MTc1NjE4NzY3NSwibmJmIjoxNzU2MTg3Njc1LCJzdWIiOiJ7XCJ0b2tlblJlZklkXCI6XCI1OTlhY2E0YS0wNzk1LTQzYjYtOWJhNC1kMjVmMjFjMjc0ZGJcIixcInZlbmRvckludGVncmF0aW9uS2V5XCI6XCJlMzFmZjIzYjA4NmI0MDZjODg3NGIyZjZkODQ5NTMxM1wiLFwidXNlckFjY291bnRJZFwiOlwiMWRmY2U1ZDQtMWUyOS00MDBiLWFkYzAtNDBkZjBiMjFlMzIwXCIsXCJkZXZpY2VJZFwiOlwiOWNiOGQwYjAtMTdkNS01YmNlLWIxZDktMWEwODQxZjI2OWRjXCIsXCJzZXNzaW9uSWRcIjpcIjVmNGVjM2RkLTRiNzMtNGExYS05OTI1LWViMWY3MzBiM2IwZFwiLFwiYWRkaXRpb25hbERhdGFcIjpcIno1NC9NZzltdjE2WXdmb0gvS0EwYk5jY1RzUU1mS0pVUmpFTUliZzdSQjFSTkczdTlLa2pWZDNoWjU1ZStNZERhWXBOVi9UOUxIRmtQejFFQisybTdRPT1cIixcInJvbGVcIjpcIm9yZGVyLWJhc2ljLGxpdmVfZGF0YS1iYXNpYyxub25fdHJhZGluZy1iYXNpYyxvcmRlcl9yZWFkX29ubHktYmFzaWNcIixcInNvdXJjZUlwQWRkcmVzc1wiOlwiMzYuMjU1LjE0LjEzMCwxNjIuMTU4LjIyNy4xODUsMzUuMjQxLjIzLjEyM1wiLFwidHdvRmFFeHBpcnlUc1wiOjE3NTYyNTQ2MDAwMDB9IiwiaXNzIjoiYXBleC1hdXRoLXByb2QtYXBwIn0.m7HFwbT3oe62zIVU1rxDQuHPdFAclCqM4vw1iVPiRlmc3j9Muy8frEBiOivcGHeLClLOtVKKqw4rc5yCcI16Bw"
TOKEN = get_token()
# print(TOKEN)

def round_to_nearest_50(value: int) -> int:
    # round to nearest multiple of 50; ties go up (e.g., 24975 -> 25000)
    r = value % 50
    return value + (50 - r) if r >= 25 else value - r


# def fetch_option_chain(request):
    """
    - Fetch NIFTY cash LTP
    - Build strikes: -100, -50, ATM, +50, +100
    - Fetch PE/CE quotes for 10 symbols concurrently
    - Save table data in OIDifference with timestamp
    """
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-API-VERSION": "1.0",
        "Accept": "application/json",
    }

    # 1) Get current NIFTY LTP
    url_ltp = "https://api.groww.in/v1/live-data/ltp?segment=CASH&exchange_symbols=NSE_NIFTY"
    try:
        nifty_resp = requests.get(url_ltp, headers=headers, timeout=5).json()
        ltp = float(nifty_resp.get("payload", {}).get("NSE_NIFTY", 0.0))
    except Exception:
        ltp = 0.0

    base_strike = round_to_nearest_50(int(ltp))
    strikes = [base_strike - 100, base_strike - 50, base_strike, base_strike + 50, base_strike + 100]

    # 2) Expiry like 25AUG
    today = timezone.localdate()
    expiry = today.strftime("%b").upper()

    # --- helper for fetching one option quote ---
    def fetch_quote(symbol, strike, opt_type):
        url_q = (
            "https://api.groww.in/v1/live-data/quote"
            f"?exchange=NSE&segment=FNO&trading_symbol={symbol}"
        )
        try:
            q = requests.get(url_q, headers=headers, timeout=5).json()
            payload = q.get("payload", {}) or {}
            oi = float(payload.get("open_interest", 0) or 0)
            prev_oi = float(payload.get("previous_open_interest", 0) or 0)
            oi_diff = oi - prev_oi
        except Exception:
            oi, prev_oi, oi_diff = 0.0, 0.0, 0.0

        # Save raw row in OptionData
        OptionData.objects.create(
            symbol=symbol,
            strike_price=strike,
            option_type=opt_type,
            open_interest=oi,
            previous_open_interest=prev_oi,
            oi_diff=oi_diff,
        )

        return (strike, opt_type, oi, oi_diff)

    # 3) Build all symbols
    tasks = []
    for strike in strikes:
        for opt_type in ["PE", "CE"]:
            symbol = f"NIFTY25{expiry}{strike}{opt_type}"
            tasks.append((symbol, strike, opt_type))

    # 4) Run all requests in parallel
    per_strike = {s: {"CE": None, "PE": None} for s in strikes}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_quote, symbol, strike, opt_type) for symbol, strike, opt_type in tasks]
        for f in concurrent.futures.as_completed(futures):
            strike, opt_type, oi, oi_diff = f.result()
            per_strike[strike][opt_type] = {"open_interest": oi, "oi_diff": oi_diff}

    # 5) Build main table + save in OIDifference
    table = []
    for strike in strikes:
        ce_oi = per_strike[strike]["CE"]["open_interest"]
        ce_diff = per_strike[strike]["CE"]["oi_diff"]
        pe_oi = per_strike[strike]["PE"]["open_interest"]
        pe_diff = per_strike[strike]["PE"]["oi_diff"]

        OIDifference.objects.create(
            strike=strike,
            ce=ce_oi,
            ce_diff=ce_diff,
            pe=pe_oi,
            pe_diff=pe_diff,
        )

        table.append({
            "strike": strike,
            "ce": ce_oi,
            "ce_diff": ce_diff,
            "pe": pe_oi,
            "pe_diff": pe_diff,
        })

    return render(request, "option_chain.html", {
        "ltp": ltp,
        "table": table,
    })
    
    
    


# def fetch_option_chain(request):
#     headers = {
#         "Authorization": f"Bearer {TOKEN}",
#         "X-API-VERSION": "1.0",
#         "Accept": "application/json",
#     }

#     # 1) Get current NIFTY LTP
#     url_ltp = "https://api.groww.in/v1/live-data/ltp?segment=CASH&exchange_symbols=NSE_NIFTY"
#     try:
#         nifty_resp = requests.get(url_ltp, headers=headers, timeout=5).json()
#         ltp = float(nifty_resp.get("payload", {}).get("NSE_NIFTY", 0.0))
#     except Exception:
#         ltp = 0.0

#     base_strike = round_to_nearest_50(int(ltp))
#     strikes = [base_strike - 100, base_strike - 50, base_strike, base_strike + 50, base_strike + 100]

#     today = timezone.localdate()
#     expiry = today.strftime("%b").upper()

#     # --- helper for fetching one option quote ---
#     def fetch_quote(symbol, strike, opt_type):
#         url_q = (
#             "https://api.groww.in/v1/live-data/quote"
#             f"?exchange=NSE&segment=FNO&trading_symbol={symbol}"
#         )
#         try:
#             q = requests.get(url_q, headers=headers, timeout=5).json()
#             payload = q.get("payload", {}) or {}
#             oi = float(payload.get("open_interest", 0) or 0)
#             prev_oi = float(payload.get("previous_open_interest", 0) or 0)
#             oi_diff = oi - prev_oi
#         except Exception:
#             oi, prev_oi, oi_diff = 0.0, 0.0, 0.0

#         OptionData.objects.create(
#             symbol=symbol,
#             strike_price=strike,
#             option_type=opt_type,
#             open_interest=oi,
#             previous_open_interest=prev_oi,
#             oi_diff=oi_diff,
#         )
#         return (strike, opt_type, oi, oi_diff)

#     # 2) Build all symbols
#     tasks = []
#     for strike in strikes:
#         for opt_type in ["PE", "CE"]:
#             symbol = f"NIFTY25{expiry}{strike}{opt_type}"
#             tasks.append((symbol, strike, opt_type))

#     # 3) Run all requests concurrently
#     per_strike = {s: {"CE": None, "PE": None} for s in strikes}
#     with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
#         futures = [executor.submit(fetch_quote, symbol, strike, opt_type) for symbol, strike, opt_type in tasks]
#         for f in concurrent.futures.as_completed(futures):
#             strike, opt_type, oi, oi_diff = f.result()
#             per_strike[strike][opt_type] = {"open_interest": oi, "oi_diff": oi_diff}

#     # 4) Save into OIDifference + main table
#     table = []
#     for strike in strikes:
#         ce_oi = per_strike[strike]["CE"]["open_interest"]
#         ce_diff = per_strike[strike]["CE"]["oi_diff"]
#         pe_oi = per_strike[strike]["PE"]["open_interest"]
#         pe_diff = per_strike[strike]["PE"]["oi_diff"]

#         OIDifference.objects.create(
#             date= timezone.localtime().date(),
#             time= timezone.localtime().time(),
#             strike=strike,
#             ce=ce_oi,
#             ce_diff=ce_diff,
#             pe=pe_oi,
#             pe_diff=pe_diff,
#         )
        
#         table.append({
#             "strike": strike,
#             "ce": ce_oi,
#             "ce_diff": ce_diff,
#             "pe": pe_oi,
#             "pe_diff": pe_diff,
#         })
    
    
    
#     now = timezone.localtime()
#     one_hour_ago = now - timedelta(hours=1)

#     # Query past hour data
#     diffs = (
#         OIDifference.objects.filter(
#             date=now.date(),
#             time__gte=one_hour_ago.time(),
#             time__lte=now.time()
#         )
#         .values("time", "strike", "ce_diff", "pe_diff")
#         .order_by("time")
#     )

#     # Track all strikes seen
#     strikes_seen = sorted({row["strike"] for row in diffs})

#     # Organize data by time
#     temp_data = {}
#     for row in diffs:
#         formatted_time = row["time"].strftime("%H:%M")
#         if formatted_time not in temp_data:
#             temp_data[formatted_time] = {}
#         temp_data[formatted_time][row["strike"]] = {
#             "CE": row["ce_diff"],
#             "PE": row["pe_diff"]
#         }

#     # Build minute-wise data for past hour
#     final_data = []
#     current_time = one_hour_ago.replace(second=0, microsecond=0)
#     last_values = {strike: {"CE": 0, "PE": 0} for strike in strikes_seen}

#     while current_time <= now:
#         formatted_time = current_time.strftime("%H:%M")
        
#         # Update last_values if we have data for this time
#         if formatted_time in temp_data:
#             for strike, vals in temp_data[formatted_time].items():
#                 last_values[strike]["CE"] = vals["CE"]
#                 last_values[strike]["PE"] = vals["PE"]

#         # Create row with nested structure
#         row_data = {
#             "time": formatted_time,
#             "strikes": []
#         }
        
#         for strike in strikes_seen:
#             # Convert to float first, then to int if it's a whole number
#             ce_val = float(last_values[strike]["CE"]) if last_values[strike]["CE"] else 0.0
#             pe_val = float(last_values[strike]["PE"]) if last_values[strike]["PE"] else 0.0
            
#             # Convert to int only if it's a whole number
#             ce_display = int(ce_val) if ce_val == int(ce_val) else ce_val
#             pe_display = int(pe_val) if pe_val == int(pe_val) else pe_val
            
#             row_data["strikes"].append({
#                 "strike": strike,
#                 "ce": ce_display,
#                 "pe": pe_display
#             })
        
#         final_data.append(row_data)
#         current_time += timedelta(minutes=1)

#     context = {
#         "data": final_data,
#         "strikes": strikes_seen
#     }

#     # print(final_data)

    
    
#     # # 5) Build last-hour time-series table
#     # now = timezone.localtime()
#     # print(now)
#     # market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
#     # market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

#     # # clamp current time within trading hours
#     # if now < market_open:
#     #     end_time = market_open
#     # elif now > market_close:
#     #     end_time = market_close
#     # else:
#     #     end_time = now.replace(second=0, microsecond=0)

#     # start_time = end_time - timedelta(minutes=59)

#     # # Query all diffs in one go
#     # diffs = OIDifference.objects.filter(
#     #     timestamp__gte=start_time,
#     #     timestamp__lte=end_time,
#     #     strike__in=strikes
#     # ).order_by("timestamp")
    
#     # # print(diffs)

#     # # organize minute-wise
#     # minute_map = { (start_time + timedelta(minutes=i)).strftime("%H:%M"): {} for i in range(60) }

#     # for d in diffs:
#     #     dt1 = timezone.localtime(d.timestamp, ist)
#     #     # print(d.timestamp)
#     #     ts = dt1.strftime("%H:%M")
#     #     minute_map.setdefault(ts, {})
#     #     minute_map[ts][f"{d.strike}CE"] = d.ce_diff
#     #     minute_map[ts][f"{d.strike}PE"] = d.pe_diff

#     # # build rows
#     # time_table = []
#     # for ts, cols in minute_map.items():
#     #     row = {"time": ts}
#     #     for strike in strikes:
#     #         row[f"{strike}CE"] = cols.get(f"{strike}CE", 0)
#     #         row[f"{strike}PE"] = cols.get(f"{strike}PE", 0)
#     #     time_table.append(row)

#     # # print(time_table)
#     # strikes_keys = []
#     # for s in strikes:
#     #     strikes_keys.append({
#     #         "strike": s,
#     #         "ce_key": f"{s}CE",
#     #         "pe_key": f"{s}PE",
#     #     })
#         # 1) Generate strikes from 27000 → 25250 step -50
# # # 1) Clamp time within market hours
# #     now = timezone.localtime()
# #     market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
# #     market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

# #     if now < market_open:
# #         end_time = market_open
# #     elif now > market_close:
# #         end_time = market_close
# #     else:
# #         end_time = now.replace(second=0, microsecond=0)

# #     start_time = end_time - timedelta(minutes=59)

# #     # 2) Query all OI differences in the last 1 hour
# #     diffs = OIDifference.objects.filter(
# #         timestamp__gte=start_time,
# #         timestamp__lte=end_time,
# #     ).order_by("timestamp")

# #     # 3) Extract unique strikes dynamically
# #     strikes = sorted(set(diffs.values_list("strike", flat=True)), reverse=True)

# #     # 4) Create minute map (60 slots)
# #     minute_map = {
# #         (start_time + timedelta(minutes=i)).strftime("%H:%M"): {} for i in range(60)
# #     }

# #     for d in diffs:
# #         ts = timezone.localtime(d.timestamp).strftime("%H:%M")
# #         minute_map.setdefault(ts, {})
# #         minute_map[ts][f"{d.strike}CE"] = d.ce_diff
# #         minute_map[ts][f"{d.strike}PE"] = d.pe_diff

# #     # 5) Build table rows dynamically
# #     time_table = []
# #     for ts, cols in minute_map.items():
# #         row = {"time": ts}
# #         for strike in strikes:
# #             row[f"{strike}CE"] = cols.get(f"{strike}CE", 0)
# #             row[f"{strike}PE"] = cols.get(f"{strike}PE", 0)
# #         time_table.append(row)

# #     # 6) Build strike keys for template
# #     strikes_keys = [
# #         {"strike": s, "ce_key": f"{s}CE", "pe_key": f"{s}PE"}
# #         for s in strikes
# #     ]
    
# #         # ✅ Print final data before rendering
# #     print("========= FINAL DATA =========")
# #     print("LTP:", ltp)
# #     print("Current Table (Latest Snapshot):")
# #     for row in table:
# #         print(row)
# #     print("\nMinute-wise Time Table (Last Hour):")
# #     for row in time_table:
# #         print(row)
# #     print("\nStrikes Keys:")
# #     for sk in strikes_keys:
# #         print(sk)
# #     print("========= END FINAL DATA =========")
    
    
#     return render(request, "option_chain.html", {
#         "ltp": ltp,
#         "table": table,
#         # "time_table": time_table,
#         "strikes": strikes,
#         "data": final_data    
#         # "strikes_keys": strikes_keys,   # ✅ new
#     })



def fetch_option_chain(request):
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-API-VERSION": "1.0",
        "Accept": "application/json",
    }

    # 1) Get current NIFTY LTP
    url_ltp = "https://api.groww.in/v1/live-data/ltp?segment=CASH&exchange_symbols=NSE_NIFTY"
    try:
        nifty_resp = requests.get(url_ltp, headers=headers, timeout=5).json()
        ltp = float(nifty_resp.get("payload", {}).get("NSE_NIFTY", 0.0))
    except Exception:
        ltp = 0.0

    base_strike = round_to_nearest_50(int(ltp))
    strikes = [base_strike - 100, base_strike - 50, base_strike, base_strike + 50, base_strike + 100]

    today = timezone.localdate()
    expiry = today.strftime("%b").upper()

    # --- helper for fetching one option quote ---
    def fetch_quote(symbol, strike, opt_type):
        url_q = (
            "https://api.groww.in/v1/live-data/quote"
            f"?exchange=NSE&segment=FNO&trading_symbol={symbol}"
        )
        try:
            q = requests.get(url_q, headers=headers, timeout=5).json()
            # print(q)
            payload = q.get("payload", {}) or {}
            oi = float(payload.get("open_interest", 0) or 0)
            prev_oi = float(payload.get("previous_open_interest", 0) or 0)
            oi_diff = oi - prev_oi
            # print(oi_diff)
        except Exception:
            oi, prev_oi, oi_diff = 0.0, 0.0, 0.0

        OptionData.objects.create(
            symbol=symbol,
            strike_price=strike,
            option_type=opt_type,
            open_interest=oi,
            previous_open_interest=prev_oi,
            oi_diff=oi_diff,
        )
        return (strike, opt_type, oi, oi_diff)

    # 2) Build all symbols
    tasks = []
    for strike in strikes:
        for opt_type in ["PE", "CE"]:
            symbol = f"NIFTY25{expiry}{strike}{opt_type}"
            tasks.append((symbol, strike, opt_type))

    # 3) Run all requests concurrently
    per_strike = {s: {"CE": None, "PE": None} for s in strikes}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_quote, symbol, strike, opt_type) for symbol, strike, opt_type in tasks]
        for f in concurrent.futures.as_completed(futures):
            strike, opt_type, oi, oi_diff = f.result()
            per_strike[strike][opt_type] = {"open_interest": oi, "oi_diff": oi_diff}

    # 4) Save into OIDifference + main table
    table = []
    for strike in strikes:
        ce_oi = per_strike[strike]["CE"]["open_interest"]
        ce_diff = per_strike[strike]["CE"]["oi_diff"]
        pe_oi = per_strike[strike]["PE"]["open_interest"]
        pe_diff = per_strike[strike]["PE"]["oi_diff"]

        OIDifference.objects.create(
            date= timezone.localtime().date(),
            time= timezone.localtime().time(),
            strike=strike,
            ce=ce_oi,
            ce_diff=ce_diff,
            pe=pe_oi,
            pe_diff=pe_diff,
        )
        
        table.append({
            "strike": strike,
            "ce": ce_oi,
            "ce_diff": ce_diff,
            "pe": pe_oi,
            "pe_diff": pe_diff,
        })
    
    
    
    now = timezone.localtime()
    one_hour_ago = now - timedelta(hours=1)
    # print(now.date())
    # print(now.time())
    # print(one_hour_ago.time())

    # Query past hour data
    diffs = (
        OIDifference.objects.filter(
            date=now.date(),
            time__gte=one_hour_ago.time(),
            time__lte=now.time()
        )
        .values("time", "strike", "ce_diff", "pe_diff")
        .order_by("time")
    )
    # print(list(diffs))
    # Track all strikes seen
    strikes_seen = sorted({row["strike"] for row in diffs})
    # print(strikes_seen)

    # Organize data by time
    temp_data = {}
    for row in diffs:
        formatted_time = row["time"].strftime("%H:%M")
        if formatted_time not in temp_data:
            temp_data[formatted_time] = {}
        temp_data[formatted_time][row["strike"]] = {
            "CE": row["ce_diff"],
            "PE": row["pe_diff"]
        }

    # Build minute-wise data for past hour
    final_data = []
    current_time = one_hour_ago.replace(second=0, microsecond=0)
    last_values = {strike: {"CE": 0, "PE": 0} for strike in strikes_seen}

    while current_time <= now:
        formatted_time = current_time.strftime("%H:%M")
        
        # Update last_values if we have data for this time
        if formatted_time in temp_data:
            for strike, vals in temp_data[formatted_time].items():
                last_values[strike]["CE"] = vals["CE"]
                last_values[strike]["PE"] = vals["PE"]

        # Create row with nested structure
        row_data = {
            "time": formatted_time,
            "strikes": []
        }
        
        for strike in strikes_seen:
            # Convert to float first, then to int if it's a whole number
            ce_val = float(last_values[strike]["CE"]) if last_values[strike]["CE"] else 0.0
            pe_val = float(last_values[strike]["PE"]) if last_values[strike]["PE"] else 0.0
            
            # Convert to int only if it's a whole number
            ce_display = int(ce_val) if ce_val == int(ce_val) else ce_val
            pe_display = int(pe_val) if pe_val == int(pe_val) else pe_val
            
            row_data["strikes"].append({
                "strike": strike,
                "ce": ce_display,
                "pe": pe_display
            })
        
        final_data.append(row_data)
        current_time += timedelta(minutes=1)

    context = {
        "data": final_data,
        "strikes": strikes_seen
    }

    # print(final_data)
    # print(strikes)
    
    return render(request, "option_chain.html", {
        "ltp": ltp,
        "table": table,
        # "time_table": time_table,
        "strikes": strikes,
        "data": final_data    
        # "strikes_keys": strikes_keys,   # ✅ new
    })
    
    
    
