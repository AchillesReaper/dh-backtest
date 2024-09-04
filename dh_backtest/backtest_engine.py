import copy
from datetime import datetime
import itertools
import multiprocessing
import os
import sys
from typing import Callable, List
from termcolor import cprint
import pandas as pd
# local modules
# from models.local_data import read_csv_with_metadata, to_csv_with_metadata
# from models.data_classes import FutureTradingAccount, Underlying
# from views.visual_bt_results import plot_app
from dh_backtest.models.local_data import read_csv_with_metadata, to_csv_with_metadata
from dh_backtest.models.data_classes import FutureTradingAccount, Underlying
from dh_backtest.views.visual_bt_results import plot_app


pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.width', None)

class BacktestEngine():
    def __init__(
            self, 
            is_update_data      :bool, 
            is_rerun_backtest   :bool, 
            underlying          :Underlying, 
            para_dict           :dict,
            trade_account       :FutureTradingAccount,
            generate_signal     :Callable, 
            action_on_signal    :Callable, 
            get_data_from_api   : Callable,
            folder_path :str = 'data/stg_1',
            plot_app    :Callable = plot_app,
        ) -> None:
        self.is_update_data     = is_update_data
        self.is_rerun_backtest  = is_rerun_backtest
        self.folder_path        = folder_path
        self.file_name          = f'{underlying.symbol}_{underlying.start_date}_{underlying.end_date}_{underlying.barSizeSetting}'.replace('-', '').replace(' ', '')   
        self.underlying         = underlying
        self.para_dict          = para_dict
        self.trade_account      = trade_account
        self.generate_signal    = generate_signal
        self.action_on_signal   = action_on_signal
        self.get_from_api       = get_data_from_api
        self.plot_app           = plot_app
        pass

    def get_hist_data(self) -> pd.DataFrame:
        '''
        choose the historical data source -> is_update_data: True(remote) / False(local)
        remote args: folder_path, file_name, underlying_datails, get_date_from_api
        local args: folder_path, file_name
        return a pandas dataframe with column ['timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume', 'rolling_gain', ].
        '''
        if not self.is_update_data and (not self.folder_path or not self.file_name):
            cprint("Error: insufficient arguments to get historical data!", 'red')
            sys.exit()
        if self.is_update_data:
            if not self.get_from_api: 
                cprint("Error: a function to get data from api is needed!", 'red')
                sys.exit()
            df_hist_data = self.get_from_api(self.underlying)
            if not os.path.exists(self.folder_path): os.makedirs(self.folder_path)
            save_file_path = os.path.join(self.folder_path, f'{self.file_name}.csv')
            df_hist_data.to_csv(save_file_path)
            cprint(f'Historical data saved to: {save_file_path}', 'green')
        else:
            try:
                df_hist_data = pd.read_csv(os.path.join(self.folder_path, f'{self.file_name}.csv'))
            except FileNotFoundError:
                cprint("Error: No historical data found!", 'red')
                sys.exit()
        return df_hist_data


    def get_all_para_combination(self) -> dict:
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
        para_values = list(self.para_dict.values())
        para_keys = list(self.para_dict.keys())
        para_list = list(itertools.product(*para_values))

        df = pd.DataFrame(para_list, columns=para_keys)

        ref_tag = [f'{self.file_name}_bt_{i+1:03d}' for i in df.index]
        df['ref_tag'] = ref_tag
        df.set_index('ref_tag', inplace=True)
        para_comb_dict = df.to_dict(orient='index')
        
        return para_comb_dict


    def init_trading(self, df_testing:pd.DataFrame) -> pd.DataFrame:
        df_testing['action']     = ''   # action: buy, sell, close
        df_testing['logic']      = ''   # logic: open, reach profit target, reach stop loss, stop loss, force close
        df_testing['t_size']     = 0    # size in the transaction
        df_testing['t_price']    = 0    # price in the transaction
        df_testing['commission'] = 0    # commission in the transaction

        df_testing['pnl_action'] = 0.0  # realised P/L from the action, including commission
        df_testing['pos_size']   = 0    # position size
        df_testing['pos_price']  = 0.0  # position average price

        df_testing['pnl_unrealized'] = float(self.trade_account.pnl_unrealized)        # unrealized profit and loss
        df_testing['nav']            = float(self.trade_account.bal_equity)            # net asset value = cash balance + unrealized profit and loss
        df_testing['bal_cash']       = float(self.trade_account.bal_cash)              # cash balance: booked equity
        df_testing['bal_avialable']  = float(self.trade_account.bal_avialable)         # cash available for trading = cash balance - initial margin + unrealized profit and loss
        df_testing['margin_initial'] = float(self.trade_account.margin_initial)        # initial margin in $ term
        df_testing['cap_usage']      = f'{self.trade_account.cap_usage:.2f}%'          # usage of the capital = initial margin / cash balance
        return df_testing


    def run_backtest(self, df_hist_data:pd.DataFrame, ref_tag:str, para_comb:dict,) -> pd.DataFrame:
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
        trading_account = copy.deepcopy(self.trade_account)
        df_hist_data_copy = df_hist_data.copy()
        underlying_copy = copy.deepcopy(self.underlying)
        df_signal = self.generate_signal(df_hist_data_copy, para_comb, underlying_copy)
        df_testing = self.init_trading(df_signal)
        df_backtest_result = self.action_on_signal(df_testing, para_comb, trading_account)
        df_backtest_result.attrs = {
            'ref_tag': ref_tag,
            'para_comb': para_comb,
            'performace_report': self.generate_bt_report(df_backtest_result),
        }
        bt_result_folder = os.path.join(self.folder_path, 'bt_results')
        to_csv_with_metadata(df=df_backtest_result, file_name=ref_tag, folder=bt_result_folder)
        return df_backtest_result


    def read_backtest_result(self) -> List[pd.DataFrame]:
        '''Read the backtest results from the the designated folder.'''
        backtest_results = []
        bt_result_path = os.path.join(self.folder_path, 'bt_results')
        file_list = list(set(file_n.split('.')[0] for file_n in os.listdir(bt_result_path)))
        for file in file_list:
            if self.file_name in file:
                cprint(f'Reading backtest result from: {file} ......', 'yellow')
                backtest_results.append(read_csv_with_metadata(file, folder=bt_result_path))
        return backtest_results


    def generate_bt_report(self, df_bt_result:pd.DataFrame, risk_free_rate:float=0.02) -> dict:
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


    def run_engine(self):
        '''
        This is the main controller to run the backtest.
        '''
        if datetime.strptime(self.underlying.end_date, "%Y-%m-%d") > datetime.today():
            cprint("Error: End date is in the future!", 'red')
            sys.exit()

        
        # get the backtest results
        backtest_results = []
        if self.is_rerun_backtest:
            # get the historical data
            df_hist_data = self.get_hist_data()
            # generate all possible combinations of the parameters
            para_comb_dict = self.get_all_para_combination()
            # run the backtest
            num_processors = multiprocessing.cpu_count()
            print(f"Running backtest with processors of: {num_processors}")
            with multiprocessing.Pool(num_processors) as pool:
                backtest_results = pool.starmap(self.run_backtest, [(df_hist_data, ref_tag, para_comb) for ref_tag, para_comb in para_comb_dict.items()])
        else:
            backtest_results = self.read_backtest_result()

        # visualize the backtest results
        cprint('plotting the backtest results......', 'green')
        self.plot_app(backtest_results)


