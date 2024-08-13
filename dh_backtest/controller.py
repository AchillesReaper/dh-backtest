from datetime import datetime
import itertools
import multiprocessing
import os
import sys
from typing import Callable, List
from termcolor import cprint
import pandas as pd
from model import get_hist_data_ib, read_csv_with_metadata, to_csv_with_metadata
from classes import FutureTradingAccount
from view import plot_app

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.width', None)


def get_hist_data(is_update_data:bool, datasource:str, underlying:dict, file_name:str) -> pd.DataFrame:
    '''
    choose a data source to get historical data.
    current available sources in this package are: IB, Futu, hkfdb
    return a pandas dataframe with column ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'rolling_gain', ].
    '''
    if is_update_data:
        df_hist_data = get_hist_data_ib(
            symbol          = underlying['symbol'],
            exchange        = underlying['exchange'],
            contract_type   = underlying['contract_type'],
            barSizeSetting  = underlying['barSizeSetting'],
            start_date      = underlying['start_date'],
            end_date        = underlying['end_date'],
            rolling_days    = underlying['rolling_days'],
        )
        if not os.path.exists('data/raw'): os.makedirs('data/raw')
        df_hist_data.to_csv(f'data/raw/{file_name}.csv')
        cprint(f'Historical data saved to: data/raw/{file_name}.csv', 'green')
    else:
        try:
            df_hist_data = pd.read_csv(f'data/raw/{file_name}.csv')
        except FileNotFoundError:
            cprint("Error: No historical data found!", 'red')
            sys.exit()
    return df_hist_data


def get_all_para_combination(para_dict: dict, file_name:str) -> dict:
    '''
    This is a function to generate all possible combinations of the parameters for the strategy.
    return a dictionary with reference tags as keys for each possible combination of the parameters.
    eg:
    arg = {'stop_loss': [10, 20, 30], 'target_profit': [10, 20, 30]}
    return {
            'ref_001': {'stop_loss': 10, 'target_profit': 10},
            'ref_002': {'stop_loss': 10, 'target_profit': 20},
            'ref_003': {'stop_loss': 10, 'target_profit': 30},
            ...
            }
    '''
    para_values = list(para_dict.values())
    para_keys = list(para_dict.keys())
    para_list = list(itertools.product(*para_values))

    df = pd.DataFrame(para_list, columns=para_keys)

    ref_tag = [f'{file_name}_bt_{i+1:08d}' for i in df.index]
    df['ref_tag'] = ref_tag
    df.set_index('ref_tag', inplace=True)
    para_comb_dict = df.to_dict(orient='index')
    
    return para_comb_dict


def init_trading(trade_account:FutureTradingAccount, df:pd.DataFrame):
    df['action']     = ''   # action: buy, sell, close
    df['logic']      = ''   # logic: open, reach profit target, reach stop loss, stop loss, force close
    df['t_size']     = 0    # size in the transaction
    df['t_price']    = 0    # price in the transaction
    df['commission'] = 0    # commission in the transaction

    df['pnl_action'] = 0.0  # realised P/L from the action, including commission
    df['pos_size']   = 0    # position size
    df['pos_price']  = 0.0  # position average price

    df['pnl_unrealized'] = float(trade_account.pnl_unrealized)        # unrealized profit and loss
    df['nav']            = float(trade_account.bal_equity)            # net asset value = cash balance + unrealized profit and loss
    df['bal_cash']       = float(trade_account.bal_cash)              # cash balance: booked equity
    df['bal_avialable']  = float(trade_account.bal_avialable)         # cash available for trading = cash balance - initial margin + unrealized profit and loss
    df['margin_initial'] = float(trade_account.margin_initial)        # initial margin in $ term
    df['cap_usage']      = f'{trade_account.cap_usage:.2f}%'          # usage of the capital = initial margin / cash balance
    return df


def generate_bt_report(df_bt_result:pd.DataFrame, risk_free_rate:float=0.02) -> dict:
    # performance metrics
    number_of_trades = df_bt_result[df_bt_result['action']=='close'].shape[0]
    win_rate = df_bt_result[df_bt_result['pnl_action'] > 0].shape[0] / df_bt_result[df_bt_result['action']=='close'].shape[0]
    total_cost = df_bt_result['commission'].sum()
    # MDD
    df_bt_result['cum_max_nav']     = df_bt_result['nav'].cummax()
    df_bt_result['dd_pct_nav']      = df_bt_result['nav'] / df_bt_result['cum_max_nav'] -1
    df_bt_result['dd_dollar_nav']   = df_bt_result['nav']- df_bt_result['cum_max_nav']
    mdd_pct_trading                 = df_bt_result['dd_pct_nav'].min()
    mdd_dollar_trading              = df_bt_result['dd_dollar_nav'].min()

    df_bt_result['cum_max_bah']     = df_bt_result['close'].cummax()
    df_bt_result['dd_pct_bah']      = df_bt_result['close'] / df_bt_result['cum_max_bah'] -1
    df_bt_result['dd_dollar_bah']   = df_bt_result['close']- df_bt_result['cum_max_bah']
    mdd_pct_bah                     = df_bt_result['dd_pct_bah'].min()
    mdd_dollar_bah                  = df_bt_result['dd_dollar_bah'].min()


    # net profit
    pnl_trading = df_bt_result['nav'].iloc[-1] - df_bt_result['nav'].iloc[0]
    roi_trading = pnl_trading / df_bt_result['nav'].iloc[0]

    pnl_bah     = df_bt_result['close'].iloc[-1] - df_bt_result['close'].iloc[0]
    roi_bah     = pnl_bah / df_bt_result['close'].iloc[0]

    # win rate

    performance_report = {
        'number_of_trades'      : int(number_of_trades),
        'win_rate'              : float(win_rate),
        'total_cost'            : float(total_cost),
        'pnl_trading'           : float(pnl_trading),
        'roi_trading'           : float(roi_trading),
        'mdd_pct_trading'       : float(mdd_pct_trading),
        'mdd_dollar_trading'    : float(mdd_dollar_trading),
        'pnl_bah'               : float(pnl_bah),
        'roi_bah'               : float(roi_bah),
        'mdd_pct_bah'           : float(mdd_pct_bah),
        'mdd_dollar_bah'        : float(mdd_dollar_bah),
    }
    return performance_report


def run_backtest(df_hist_data:pd.DataFrame, ref_tag:str, para_comb:dict, generate_signal:Callable, action_on_signal:Callable) -> pd.DataFrame:
    '''
    This is a function to run backtest on the strategy.
    Return a pandas dataframe with 
        index: timestamp
        columns: ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'rolling_gain', 'calculation_col_1', 'calculation_col_2', 'signal', 'action', 'logic', 't_price', 't_size', 'commission', 'pnl_action', 'acc_columns'].
        metadata: {
            'ref_tag':      ref_tag,
            'para_comb':    para_comb,
            'performace_report': {
                'number_of_trades':     0,
                'win_rate':             0,
                'total_cost':           0,
                'pnl_trading':          0,
                'roi_trading':          0,
                'mdd_pct_trading':      0,
                'mdd_dollar_trading':   0,
                'pnl_bah':              0,
                'roi_bah':              0,
                'mdd_pct_bah':          0,
                'mdd_dollar_bah':       0,
            },
            benchmark:{
                'roi_sp500':            0,
                'roi_tbill_52w':        0,
            }
        }
    '''
    cprint(f"Running backtest for {ref_tag}", 'green')
    df_signal = generate_signal(df_hist_data, para_comb)
    df_backtest_result = action_on_signal(df_signal, para_comb)
    df_backtest_result.attrs = {
        'ref_tag': ref_tag,
        'para_comb': para_comb,
        'performace_report': generate_bt_report(df_backtest_result),
    }
    to_csv_with_metadata(df=df_backtest_result, file_name=ref_tag)
    return df_backtest_result


def read_backtest_result(file_name:str) -> List[pd.DataFrame]:
    '''Read the backtest results from the csv files in folder "data/backtest".'''
    backtest_results = []
    file_list = list(set(file_n.split('.')[0] for file_n in os.listdir('data/backtest')))
    for file in file_list:
        if file_name in file:
            cprint(f'Reading backtest result from: {file} ......', 'yellow')
            backtest_results.append(read_csv_with_metadata(file))
    return backtest_results



def main_controller(is_update_data:bool, is_rerun_backtest:bool, datasource:str, underlying:dict, para_dict:dict, generate_signal:Callable, action_on_signal:Callable):
    '''
    This is the main controller to run the backtest.
    '''
    if datetime.strptime(underlying['end_date'], "%Y-%m-%d") > datetime.today():
        cprint("Error: End date is in the future!", 'red')
        sys.exit()

    file_name = f'{underlying["symbol"]}_{underlying["start_date"].replace('-','')}_{underlying["end_date"].replace('-','')}_{underlying['barSizeSetting'].replace(' ','')}'
    # get the backtest results
    backtest_results = []
    if is_rerun_backtest:
        # get the historical data
        df_hist_data = get_hist_data(is_update_data, datasource, underlying, file_name)
        # generate all possible combinations of the parameters
        para_comb_dict = get_all_para_combination(para_dict, file_name)
        # run the backtest
        num_processors = multiprocessing.cpu_count()
        print(f"Running backtest with processors of: {num_processors}")
        with multiprocessing.Pool(num_processors) as pool:
            backtest_results = pool.starmap(run_backtest, [(df_hist_data, ref_tag, para_comb, generate_signal, action_on_signal) for ref_tag, para_comb in para_comb_dict.items()])
    else:
        backtest_results = read_backtest_result(file_name)

    # visualize the backtest results
    cprint('plotting the backtest results......', 'green')
    plot_app(backtest_results)

    
