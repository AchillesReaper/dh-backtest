import json
import os
import sys
from typing import List
from termcolor import cprint

from datetime import datetime
from dateutil.relativedelta import relativedelta
import arrow
import pytz

import pandas as pd
from ib_insync import IB, Contract
from futu import OpenQuoteContext, KLType, AuType, KL_FIELD, RET_OK
# local imports
# from data_classes import IBBarSize, Underlying
from .data_classes import IBBarSize, Underlying

##### ***** commom functions ***** #####
def get_month_list(start_date: str, end_date: str):
    start_date      = datetime.strptime(start_date, "%Y-%m-%d")
    end_date        = datetime.strptime(end_date, "%Y-%m-%d")
    month_list      = []
    current_date    = start_date
    while current_date <= end_date:
        month_list.append(current_date.strftime("%Y%m"))
        current_date += relativedelta(months=1)
    return month_list


def combine_spot_iter_data(iter_df_list):
    # combine the spot data from different contract months
    cprint("Combining spot months data ... ...", "green")
    df = pd.DataFrame()
    for i in range(len(iter_df_list)):
        first_row_index = iter_df_list[i].index[0]
        print(f'iter first trade date: {iter_df_list[i]["trade_date"].tolist()[0]}')

        if i > 0:
            first_row_index = iter_df_list[i].index[0]
            rolling_gain = iter_df_list[i-1]["open"].tolist()[-1] - iter_df_list[i]["open"].tolist()[0]
            iter_df_list[i].loc[first_row_index, "rolling_gain"] = rolling_gain
            cprint(f"rolling date: {iter_df_list[i]['trade_date'].tolist()[0]}, with gain: {rolling_gain}", 'yellow')

        if i != len(iter_df_list) - 1:
            df = df._append(iter_df_list[i].iloc[0:-2])
        else:
            df = df._append(iter_df_list[i])
    return df


##### ***** IB ***** #####
def get_spot_iter_from_ib(underlying:Underlying, contract_month:str) -> pd.DataFrame:
    '''
    This function gets the spot contract trading data from IB API, with (host='127.0.0.1', port=4002, clientId=1)
    return dataframe with columns: ["datetime", "timestamp", "open", "high", "low", "close", "volume", "barCount", "average", "expiry", "trade_date"]
    '''
    # get the spot contract trading data from IB API, return df 
    ib = IB()
    ib.connect("127.0.0.1", 4002, clientId=1)

    # step 1: get the contract object
    spot_contract                              = Contract()
    spot_contract.symbol                       = underlying.symbol
    spot_contract.exchange                     = underlying.exchange
    spot_contract.secType                      = underlying.contract_type
    spot_contract.includeExpired               = True
    spot_contract.lastTradeDateOrContractMonth = contract_month
    try:
        spot_contract = ib.reqContractDetails(spot_contract)[0].contract
    except Exception as e:
        cprint(f"Error: {e}", "red")
        cprint(f"Spot contract, expired {spot_contract.lastTradeDateOrContractMonth}, not found", "red")
        sys.exit()
    
    cprint(f"Spot contract, expired {spot_contract.lastTradeDateOrContractMonth}, constructed", "green")

    # step 2: get the historical data from IB
    endDateTime = arrow.get(spot_contract.lastTradeDateOrContractMonth, "YYYYMMDD").replace(hour=17,tzinfo=underlying.timeZone)
    endDateTime = int(endDateTime.timestamp())
    endDateTime = datetime.fromtimestamp(endDateTime, pytz.timezone(underlying.timeZone))

    bars = ib.reqHistoricalData(
        spot_contract,
        endDateTime     = endDateTime,
        durationStr     = underlying.durationStr,
        barSizeSetting  = underlying.barSizeSetting,
        whatToShow      = "TRADES",
        useRTH          = False,            # True: Regular trading hours only
        formatDate      = 2,
    )
    # extract data from the bars into a pandas DataFrame
    data = []
    if underlying.barSizeSetting.split()[1] in ('secs', 'min ', 'mins', 'hour', 'hours'):
        # for intraday data
        for bar in bars:
            bar_timestamp = int(bar.date.timestamp())
            nominal_trade_date = datetime.fromtimestamp(bar_timestamp-4*3600).astimezone(pytz.timezone(underlying.timeZone)).strftime("%Y-%m-%d")

            row = (
                bar.date.astimezone(pytz.timezone(underlying.timeZone)),
                bar_timestamp,
                int(bar.open),
                int(bar.high),
                int(bar.low),
                int(bar.close),
                int(bar.volume),
                int(bar.barCount),
                bar.average,
                spot_contract.lastTradeDateOrContractMonth,
                nominal_trade_date,
            )
            data.append(row)
        iter_df = pd.DataFrame(data, columns=["datetime", "timestamp", "open", "high", "low", "close", "volume", "barCount", "average", "expiry", "trade_date"])
    elif underlying.barSizeSetting.split()[1] == 'day':    
        # for overnight data
        for bar in bars:
            # for day data
            bar_timestamp = datetime.strptime(str(bar.date), "%Y-%m-%d").replace(hour=9).timestamp()

            row = (
                bar.date,
                bar_timestamp,
                int(bar.open),
                int(bar.high),
                int(bar.low),
                int(bar.close),
                int(bar.volume),
                int(bar.barCount),
                bar.average,
                spot_contract.lastTradeDateOrContractMonth,
                bar.date.strftime("%Y-%m-%d"),
            )
            data.append(row)
        iter_df = pd.DataFrame(data, columns=["datetime", "timestamp", "open", "high", "low", "close", "volume", "barCount", "average", "expiry", "trade_date"])
    else:
        cprint(f"Error: barSizeSetting {underlying.barSizeSetting} not supported", "red")
        sys.exit()
    ib.disconnect()

    iter_df.set_index("timestamp", inplace=True)

    # step 3: trim the data
    trade_date_list = iter_df["trade_date"].unique().copy()

    i = 0
    for trade_date in trade_date_list:
        if datetime.strptime(trade_date, "%Y-%m-%d").strftime("%Y%m") == contract_month:
            #trade_date_list[i] is the first day of the contract month
            iter_start_date = trade_date_list[i-underlying.rolling_days-1]  
            i=0
            break
        i+=1

    for index, row in iter_df.iterrows():
        if row["trade_date"] == iter_start_date:
            iter_start_index = index
            break
    if datetime.strptime(underlying.end_date, "%Y-%m-%d").strftime("%Y%m") == contract_month:
        # for the last contract month over the testing period
        iter_end_date = underlying.end_date
        iter_end_index = iter_df.index[-1]
    else:
        # for the other contract months over the testing period
        iter_end_date = trade_date_list[-underlying.rolling_days]
        for index, row in iter_df.iterrows():
            if row["trade_date"] == iter_end_date:
                iter_end_index = index
                break

    iter_df = iter_df.loc[iter_start_index:iter_end_index].copy()
    iter_df['rolling_gain'] = 0
    return iter_df

def get_spot_future_ib(underlying:Underlying) -> pd.DataFrame:
    '''
    return df: index="timestamp", columns=["datetime", , "open", "high", "low", "close", "volume", "barCount", "average", "expiry", "trade_date"]
    '''
    # get the spot contract trading data from IB API, return df 
    month_list = get_month_list(underlying.start_date, underlying.end_date)
    iter_df_list = []
    for contract_month in month_list:
        iter_df = get_spot_iter_from_ib(underlying, contract_month)
        iter_df_list.append(iter_df)
    spot_df = combine_spot_iter_data(iter_df_list)
    return spot_df



##### ***** futu ***** #####
def get_stock_futu(underlying:Underlying) -> pd.DataFrame:
    '''
    This function gets the spot contract trading data from futu-api, with (host='127.0.0.1', port=11111)
    return dataframe with columns: ["datetime", "timestamp", "open", "high", "low", "close", "volume", "barCount", "average", "expiry", "trade_date"]
    '''

    futu_client = OpenQuoteContext(host='127.0.0.1', port=11111)
    ret, data, page_req_key = futu_client.request_history_kline(
        code        = underlying.symbol,
        start       = underlying.start_date,
        end         = underlying.end_date,
        ktype       = underlying.barSizeSetting,
        autype      = AuType.QFQ, 
        fields      = [KL_FIELD.DATE_TIME, KL_FIELD.OPEN, KL_FIELD.HIGH, KL_FIELD.LOW, KL_FIELD.CLOSE], 
        max_count   =1000, 
        page_req_key=None, 
        extended_time=True
    )
    return data





# test the functions
if __name__ == "__main__":
    underlying = Underlying(
        symbol          = "HK.00388",
        exchange        = "HKFE",
        contract_type   = "FUT",
        barSizeSetting  = KLType.K_30M,
        start_date      = "2023-01-01",
        end_date        = "2023-07-31",
        durationStr     = "2 M",
        rolling_days    = 4,
        timeZone        = "Asia/Hong_Kong",
    )

    df_stock = get_stock_futu(underlying)
    print(df_stock)

