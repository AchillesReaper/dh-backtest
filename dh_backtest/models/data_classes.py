import numpy as np
import sys
from termcolor import cprint

class Underlying():
    def __init__(self, symbol:str, exchange:str, contract_type:str, barSizeSetting:str,start_date:str, end_date:str,  durationStr='2 M', rolling_days:int=4, timeZone:str="Asia/Hong_Kong"):
        self.symbol             = symbol
        self.exchange           = exchange
        self.contract_type      = contract_type
        self.barSizeSetting     = barSizeSetting
        self.start_date         = start_date        # 'YYYY-MM-DD' -> '2023-01-01'
        self.end_date           = end_date          # 'YYYY-MM-DD' -> '2023-07-31'
        self.durationStr        = durationStr
        self.rolling_days       = rolling_days
        self.timeZone           = timeZone


class IBBarSize():
    SEC_1   = '1 secs'
    SEC_5   = '5 secs'
    SEC_10  = '10 secs'
    SEC_15  = '15 secs'
    SEC_30  = '30 secs'
    MIN_1   = '1 min'
    MIN_2   = '2 mins'
    MIN_3   = '3 mins'
    MIN_5   = '5 mins'
    MIN_10  = '10 mins'
    MIN_15  = '15 mins'
    MIN_20  = '20 mins'
    MIN_30  = '30 mins'
    HOUR_1  = '1 hour'
    HOUR_2  = '2 hours'
    HOUR_3  = '3 hours'
    HOUR_4  = '4 hours'
    HOUR_8  = '8 hours'
    DAY_1   = '1 day'
    WEEK_1  = '1 week'
    MONTH_1 = '1 month'


class FutureTradingAccount():
    def __init__(self, initail_cash_bal: np.float64, margin_rate:np.float64 = 0.1, commission_rate:np.float64 = 11, contract_multiplier:np.int64 = 50):
        self.bal_initial            = initail_cash_bal
        self.bal_cash               = initail_cash_bal          # cash balance
        self.bal_avialable          = initail_cash_bal          # cash available for trading = cash balance - initial margin + unrealized profit and loss
        self.bal_equity             = initail_cash_bal          # total equity(NAV) = cash balance + unrealized profit and loss
        self.pnl_unrealized         = 0                         # unrealized profit and loss
        self.margin_rate            = margin_rate               # margin rate for opening a position
        self.margin_initial         = 0                         # initial margin in $ term
        self.cap_usage              = 0                         # usage of the capital = initial margin / cash balance
        self.margin_maintanence_rate = 0.8                      # margin call level
        self.margin_force_close_rate = 0.6                      # margin force close level
        self.contract_multiplier    = contract_multiplier       # contract multiplier for the future
        self.commission_rate        = commission_rate
        self.position_size          = 0                         # position size -> number of contracts. note: -ve denotes short position
        self.position_price         = 0                         # position price -> the averave price of the current position

    def mark_to_market(self, mk_price):
        if self.position_size > 0:
            self.pnl_unrealized = (mk_price - self.position_price) * self.position_size * self.contract_multiplier
        elif self.position_size < 0:
            self.pnl_unrealized = (self.position_price - mk_price) * self.position_size * self.contract_multiplier
        else:
            self.pnl_unrealized = 0

        self.margin_initial = abs(self.position_size) * mk_price * self.contract_multiplier * self.margin_rate
        self.bal_avialable  = self.bal_cash - self.margin_initial + self.pnl_unrealized
        self.bal_equity     = self.bal_cash + self.pnl_unrealized
        self.cap_usage      = round(self.margin_initial / (self.bal_cash + 0.0001), 4)
        
        if self.bal_equity < self.margin_initial * self.margin_maintanence_rate:
            cprint(f"Warning! Margin call: ${self.margin_initial - self.bal_equity}, Margin-level: {(self.bal_equity / self.margin_initial * 100):.2f}%, ", "red")
            return {'signal': 'margin call', 'action': None}
        if self.bal_equity < self.margin_initial * self.margin_force_close_rate:
            cprint(f"Warning! Force Closure!!! \nMargin-level: {(self.bal_equity / self.margin_initial * 100):.2f}%, ", "red")
            commission, pnl_realized = self.close_position(self.position_size, mk_price)
            return {'signal': 'margin call', 'action': 'close', 'logic':'force close' , 'commission': commission, 'pnl_realized': pnl_realized}

        return {'signal': '', 'action': None}

    def open_position(self, t_size:int, t_price:float):
        # new position size shall have the same sign as the current position size
        if t_size == 0 or self.position_size/t_size < 0:
            cprint("Error: New position size is 0 or direction is wrong", "red")
            sys.exit()

        self.position_price  = (self.position_size * self.position_price + t_size * t_price) / (self.position_size + t_size)
        self.position_size  += t_size
        commission           = abs(t_size) * self.commission_rate
        self.bal_cash       -= commission
        self.mark_to_market(t_price)
        return commission


    def close_position(self, t_size:int, t_price:float):
        # assume the t_size comes in with direction => t_size must have the opposite sign of the position size
        if t_size == 0 or self.position_size/t_size > 0:
            cprint("Error: Close position size is 0 or direction is wrong", "red")
            sys.exit()

        self.position_size  += t_size
        commission           = abs(t_size) * self.commission_rate

        if t_size > 0:
            pnl_realized = (t_price - self.position_price) * t_size * self.contract_multiplier - commission
        else:
            pnl_realized = (self.position_price - t_price) * t_size * self.contract_multiplier - commission
        
        self.bal_cash += pnl_realized
        self.mark_to_market(t_price)
        return commission, pnl_realized
        
