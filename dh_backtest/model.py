'''
This module contains the functions to get historical data from included data sources.
Currently, only IB data source is supported.
'''
import json
import os
import sys
from termcolor import cprint

from datetime import datetime
from dateutil.relativedelta import relativedelta
import arrow
import pytz

from ib_insync import IB, Contract
import pandas as pd

##### ***** Get Data ***** #####

def get_month_list(start_date: str, end_date: str):
    start_date      = datetime.strptime(start_date, "%Y-%m-%d")
    end_date        = datetime.strptime(end_date, "%Y-%m-%d")
    month_list      = []
    current_date    = start_date
    while current_date <= end_date:
        month_list.append(current_date.strftime("%Y%m"))
        current_date += relativedelta(months=1)
    return month_list


def get_spot_iter_from_ib(symbol, exchange, contract_type, contract_month, barSizeSetting, 
                          start_date, end_date, 
                          durationStr='2 M', rolling_days=4, timeZone="Asia/Hong_Kong"):
    # get the spot contract trading data from IB API, return df 
    ib = IB()
    ib.connect("127.0.0.1", 4002, clientId=1)

    # step 1: get the contract object
    spot_contract                              = Contract()
    spot_contract.symbol                       = symbol
    spot_contract.exchange                     = exchange
    spot_contract.secType                      = contract_type
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
    endDateTime = arrow.get(spot_contract.lastTradeDateOrContractMonth, "YYYYMMDD").replace(hour=17,tzinfo=timeZone)
    endDateTime = int(endDateTime.timestamp())
    endDateTime = datetime.fromtimestamp(endDateTime, pytz.timezone(timeZone))

    bars = ib.reqHistoricalData(
        spot_contract,
        endDateTime     = endDateTime,
        durationStr     = durationStr,
        barSizeSetting  = barSizeSetting,
        whatToShow      = "TRADES",
        useRTH          = False,            # True: Regular trading hours only
        formatDate      = 2,
    )
    # extract data from the bars into a pandas DataFrame
    data = []
    if barSizeSetting.split()[1] in ('secs', 'min ', 'mins', 'hour', 'hours'):
        # for intraday data
        for bar in bars:
            bar_timestamp = int(bar.date.timestamp())
            nominal_trade_date = datetime.fromtimestamp(bar_timestamp-4*3600).astimezone(pytz.timezone(timeZone)).strftime("%Y-%m-%d")

            row = (
                bar.date.astimezone(pytz.timezone(timeZone)),
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
    elif barSizeSetting.split()[1] == 'day':    
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

            )
            data.append(row)
        iter_df = pd.DataFrame(data, columns=["trade_date", "timestamp", "open", "high", "low", "close", "volume", "barCount", "average", "expiry"])
    else:
        cprint(f"Error: barSizeSetting {barSizeSetting} not supported", "red")
        sys.exit()
    ib.disconnect()

    iter_df.set_index("timestamp", inplace=True)

    # step 3: trim the data
    trade_date_list = iter_df["trade_date"].unique().copy()

    i = 0
    for trade_date in trade_date_list:
        if datetime.strptime(trade_date, "%Y-%m-%d").strftime("%Y%m") == contract_month:
            iter_start_date = trade_date_list[i-1-rolling_days]
            i=0
            break
        i+=1

    for index, row in iter_df.iterrows():
        if row["trade_date"] == iter_start_date:
            iter_start_index = index
            break
    if datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y%m") == contract_month:
        iter_end_date = end_date
        iter_end_index = iter_df.index[-1]
    else:
        iter_end_date = trade_date_list[-rolling_days]
        for index, row in iter_df.iterrows():
            if row["trade_date"] == iter_end_date:
                iter_end_index = index
                break

    iter_df = iter_df.loc[iter_start_index:iter_end_index].copy()
    iter_df['rolling_gain'] = 0
    return iter_df


def combine_spot_iter_ib_data(iter_df_list, start_date:str, end_date:str):
    # combine the spot data from different contract months
    cprint(f"Combining spot data from {start_date} to {end_date}", "green")
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
    
    # file_path = f'data_bt_mp/HSI_{start_date}_{end_date}_30mins.csv'   
    # df.to_csv(file_path)
    # cprint(f'Combined spot data saved to {file_path}', 'green')
    return df


def get_hist_data_ib(symbol, exchange, contract_type, barSizeSetting, start_date, end_date, durationStr="2 M", rolling_days=4, timeZone="Asia/Hong_Kong"):
    # get the historical data from IB API
    iter_df_list = []
    
    month_list = get_month_list(start_date, end_date)
    for contract_month in month_list:
        # collect data from IB API
        iter_df = get_spot_iter_from_ib(
            symbol          = symbol,
            exchange        = exchange,
            contract_type   = contract_type,
            contract_month  = contract_month,
            barSizeSetting  = barSizeSetting,
            start_date      = start_date,
            end_date        = end_date,
            durationStr     = durationStr,
            rolling_days    = rolling_days,
            timeZone        = timeZone,
        )
        iter_df_list.append(iter_df)

    df = combine_spot_iter_ib_data(iter_df_list, start_date, end_date)

    return df


##### ***** Get Benchmark Data ***** #####

def get_risk_free_rate(start_date):
    # get the risk free rate from IB API
    target_year = int(start_date.split("-")[0])
    target_month = start_date[0:7]
    t_bill_path = f'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{target_year}/all?field_tdr_date_value={target_year}&type=daily_treasury_bill_rates&page&_format=csv'
    df_t_bill = pd.read_csv(t_bill_path, index_col=0)
    df_t_bill.index = pd.to_datetime(df_t_bill.index)
    start_month_rates = df_t_bill[df_t_bill.index.to_period('M') == pd.Period(target_month)]
    risk_free_rate = start_month_rates["52 WEEKS COUPON EQUIVALENT"].mean()
    print(df_t_bill["52 WEEKS COUPON EQUIVALENT"])
    print(f"Risk free rate on {start_date}: {risk_free_rate}")


##### ***** Get & Set local Data ***** #####

def to_csv_with_metadata(df:pd.DataFrame, folder:str, file_name:str):
    if not os.path.exists(folder): os.makedirs(folder)
    path_name = f'{folder}/{file_name}'
    df.to_csv(f'{path_name}.csv', index=True)
    with open(f'{path_name}.json', 'w') as f:
        json.dump(df.attrs, f)
        f.close()
    cprint(f'DataFrame saved to {path_name}.csv', 'yellow')
    cprint(f'Metadata saved to {path_name}.json', 'green')


def read_csv_with_metadata(path_name:str):
    df = pd.read_csv(f'{path_name}.csv', index_col=0)
    with open(f'{path_name}.json', 'r') as f:
        df.attrs = json.load(f)
        f.close()
    return df


if __name__ == "__main__":
    get_risk_free_rate("2021-01-01")