from typing import List
import pandas as pd
import dash
from dash import Dash, html, dcc, Output, Input, State, dash_table
from dash.exceptions import PreventUpdate
from model import get_bt_result_file_name, read_csv_with_metadata
from plotly import graph_objects as go
from plotly.subplots import make_subplots
from termcolor import cprint

df_performance  = ''
df_para         = ''


def plot_app(df_list: List[pd.DataFrame]):
    fig = go.Figure()
    global df_performance
    df_performance = pd.DataFrame(columns=['ref_tag', 'number_of_trades', 'win_rate', 'total_cost', 'pnl_trading', 'roi_trading', 'mdd_pct_trading', 'mdd_dollar_trading', 'pnl_bah', 'roi_bah', 'mdd_pct_bah', 'mdd_dollar_bah'])
    
    global df_para
    df_para_columns = ['ref_tag'] + (list(df_list[0].attrs['para_comb'].keys()))
    df_para = pd.DataFrame(columns=df_para_columns)

    for df in df_list:
        fig.add_trace(go.Scatter(
            x       = df['datetime'], 
            y       = df['nav'], 
            mode    = 'lines', 
            name    = 'nav',
            line    = {'width': 2},
            customdata = [df.attrs['ref_tag']] * len(df),
            text    =   f'Ref: {df.attrs["ref_tag"]} <br>' +
                        f'total_trades: {df.attrs["performace_report"]["number_of_trades"]} <br>' +
                        f'win_rate: {df.attrs["performace_report"]["win_rate"]:.2f} <br>' +
                        f'total_cost: {df.attrs["performace_report"]["total_cost"]:,.2f} <br>' +
                        f'pnl $: {df.attrs["performace_report"]["pnl_trading"]:,.2f} <br>' +
                        f'roi %: {df.attrs["performace_report"]["roi_trading"]:.2%} <br>' +
                        f'mdd $: {df.attrs["performace_report"]["mdd_dollar_trading"]:,.2f} <br>' +
                        f'mdd %: {df.attrs["performace_report"]["mdd_pct_trading"]:.2%} <br>' +
                        f'roi(trading-B&H) %: {(df.attrs["performace_report"]["roi_trading"]-df.attrs["performace_report"]["roi_bah"]):.2%} <br>' +
                        f'mdd(trading-B&H) %: {(df.attrs["performace_report"]["mdd_pct_trading"]-df.attrs["performace_report"]["mdd_pct_bah"]):.2%} <br>',
            hoverinfo='text',
        ))

        df_performance.loc[df.attrs['ref_tag']] = [
            df.attrs['ref_tag'],
            df.attrs['performace_report']['number_of_trades'],
            df.attrs['performace_report']['win_rate'],
            df.attrs['performace_report']['total_cost'],
            df.attrs['performace_report']['pnl_trading'],
            df.attrs['performace_report']['roi_trading'],
            df.attrs['performace_report']['mdd_pct_trading'],
            df.attrs['performace_report']['mdd_dollar_trading'],
            df.attrs['performace_report']['pnl_bah'],
            df.attrs['performace_report']['roi_bah'],
            df.attrs['performace_report']['mdd_pct_bah'],
            df.attrs['performace_report']['mdd_dollar_bah']
        ]

        df_para.loc[df.attrs['ref_tag']] = [df.attrs['ref_tag']] + list(df.attrs['para_comb'].values())


    fig.update_layout(
        height=800,
        showlegend=False,
        hovermode='closest',
    )

    

    app = Dash()

    money       = dash_table.FormatTemplate.money(2)
    percentage  = dash_table.FormatTemplate.percentage(2)
    style_body_sub_div = {'display': 'inline-block', 'width': '35%', 'margin-top': '10px','margin-left': 'auto', 'margin-right': 'auto'}

    app.layout = html.Div(
        style    = {'backgroundColor': '#D0B8A8'},
        children = [
            html.Div(
                id          ="header", 
                className   ='row', 
                children    ='Backtest Result',
                style       ={'height': '5vh','textAlign': 'center', 'fontSize': 30, 'fontfamily': 'Arial', 'margin': 'auto', 'padding': '10px'}
            ),
            html.Div(
                id      ='body',
                style   ={'backgroundColor': '#DFD3C3', 'height': '90vh','width': '100%', 'border': '1px solid blue', 'display': 'flex', 'justify-content': 'space-around'},
                children=[
                    dcc.Store(id='current_ref', data=''),
                    html.Div(
                        id      ='graph-area',
                        style = {**style_body_sub_div, 'width': '60%'},
                        children= [
                            dcc.Graph(id='all_equity_curve', figure=fig, style={'backgroundColor': '#F8EDE3'}),
                        ]
                    ),
                    html.Div(
                        style={**style_body_sub_div, 'width': '35%'},
                        children = [
                            html.Div(
                                style={'width': '100%', 'border': '1px solid red'},
                                children = [
                                    dash_table.DataTable(
                                        id='bt_result_table',
                                        data=df_performance[['ref_tag', 'pnl_trading', 'roi_trading', 'mdd_pct_trading']].to_dict('records'),
                                        columns=[
                                            {'name': 'Backtest Reference', 'id': 'ref_tag'},
                                            {'name': 'Profit/Loss', 'id': 'pnl_trading', 'type': 'numeric', 'format': money},
                                            {'name': 'ROI', 'id': 'roi_trading', 'type': 'numeric', 'format': percentage},
                                            {'name': 'MDD', 'id': 'mdd_pct_trading', 'type': 'numeric', 'format': percentage},
                                        ],
                                        sort_by=[{'column_id': 'roi_trading', 'direction': 'desc'}],
                                        sort_action='native',
                                        style_cell={'textAlign': 'left'},
                                        style_cell_conditional=[
                                            {'if': {'column_id': 'pnl_trading'}, 'textAlign': 'right'},
                                            {'if': {'column_id': 'roi_trading'}, 'textAlign': 'right'},
                                            {'if': {'column_id': 'mdd_pct_trading'}, 'textAlign': 'right'},

                                        ],
                                        style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'},
                                        page_size=8,
                                    )
                                ]
                            ),
                            html.Div(
                                id='performance_table',
                                style={'width': '100%', 'border': '1px solid red'},
                                children=[]
                            ),
                            html.Div(
                                id='para_table',
                                style={'width': '100%', 'border': '1px solid blue'},
                                children=[]
                            )
                        ]
                    ),
                ]
            ),
            html.Div(
                id='footer',
                style={'width': '100%'},
                children='Footer'
            )
        ]
    )


    @app.callback(
        Output('bt_result_table', 'data'),
        [Input('bt_result_table', 'sort_by')],
        State('bt_result_table', 'data')
    )
    def update_table_data(sort_by, tableData):
        if not sort_by:
            raise PreventUpdate

        df = pd.DataFrame(tableData)
        for sort in sort_by:
            df = df.sort_values(by=sort['column_id'], ascending=(sort['direction'] == 'asc'))

        return df.to_dict('records')

    # update state of current reference
    @app.callback(
        Output('current_ref', 'data'),
        [Input('all_equity_curve', 'clickData'), Input('bt_result_table', 'active_cell'),],
        State('bt_result_table', 'data')
    )
    def update_current_ref(clickData, active_cell, tableData):

        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if trigger_id == 'all_equity_curve' and clickData:
            ref_tag = clickData['points'][0]['customdata']
            return ref_tag
        
        if trigger_id == 'bt_result_table' and active_cell:
            ref_tag = tableData[active_cell['row']]['ref_tag']
            return ref_tag
    
    
    # consquence of updating the current reference state
    @app.callback(
        Output('all_equity_curve', 'figure'),
        Input('current_ref', 'data'),
        State('all_equity_curve', 'figure')
    )
    def update_line_thickness(current_ref, figure):
        if not current_ref:
            raise PreventUpdate
        for trace in figure['data']:
            if trace['customdata'][0] == current_ref:
                trace['line']['width'] = 5
                trace['opacity'] = 1
            else:
                trace['line']['width'] = 2
                trace['opacity'] = 0.7
        return figure

    @app.callback(
        Output('bt_result_table', 'style_data_conditional'),
        Input('current_ref', 'data'),
        State('bt_result_table', 'style_data_conditional')
    )
    def update_row_bg_color(current_ref, data):
        if not current_ref:
            raise PreventUpdate
        style_data_conditional = [{
            'if': {'filter_query': f'{{ref_tag}} eq "{current_ref}"'},
            'backgroundColor': 'lightblue'
        }]
        return style_data_conditional
    

    @app.callback(
        Output('performance_table', 'children'),
        Input('current_ref', 'data'),
        State('performance_table', 'children')
    )
    def show_individual_performance(current_ref, data):
        if not current_ref:
            raise PreventUpdate
        
        global df_performance
        df_table1 = pd.DataFrame(
            {
                'Reference':['Number of Trades', 'Win Rate', 'Total Cost', 'PnL Trading', 'ROI Trading'],
                current_ref:[
                    f'{df_performance.loc[current_ref]["number_of_trades"]:,}',
                    f'{df_performance.loc[current_ref]["win_rate"]:.2%}',
                    f'{df_performance.loc[current_ref]["total_cost"]:,.2f}',
                    f'{df_performance.loc[current_ref]["pnl_trading"]:,.2f}',
                    f'{df_performance.loc[current_ref]["roi_trading"]:.2%}',
                ]
            },
        )
        df_table2 = pd.DataFrame(
            {
                'Metrics':['Profit/Loss', 'Return on Investment', 'MDD Dollar', 'MDD Percentage' ],
                'Trading':[
                    f'{df_performance.loc[current_ref]["pnl_trading"]:,.2f}',
                    f'{df_performance.loc[current_ref]["roi_trading"]:.2%}',
                    f'{df_performance.loc[current_ref]["mdd_dollar_trading"]:,.2f}',
                    f'{df_performance.loc[current_ref]["mdd_pct_trading"]:.2%}',
                ],
                'Buy & Hold':[
                    f'{df_performance.loc[current_ref]["pnl_bah"]:,.2f}',
                    f'{df_performance.loc[current_ref]["roi_bah"]:.2%}',
                    f'{df_performance.loc[current_ref]["mdd_dollar_bah"]:,.2f}',
                    f'{df_performance.loc[current_ref]["mdd_pct_bah"]:.2%}',
                ]
            },
        )

        table1 = dash_table.DataTable(
            data=df_table1.to_dict('records'),
            style_cell={'textAlign': 'left'},
            style_cell_conditional=[
                {'if': {'column_id': current_ref}, 'textAlign': 'right'},
            ],
            style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'},
        )
        table2 = dash_table.DataTable(
            data=df_table2.to_dict('records'),
            style_cell={'textAlign': 'left'},
            style_cell_conditional=[
                {'if': {'column_id': 'Metrics'}, 'fontWeight': 'bold', 'textAlign': 'left'},
                {'if': {'column_id': 'Trading'}, 'backgroundColor': 'lightblue', 'textAlign': 'right'},
                {'if': {'column_id': 'Buy & Hold'}, 'backgroundColor': 'lightgreen', 'textAlign': 'right'}
            ],
            style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'},
        )
        return [table1, table2]


    @app.callback(
        Output('para_table', 'children'),
        Input('current_ref', 'data'),
        State('para_table', 'children')
    )
    def show_parameters(current_ref, data):
        if not current_ref:
            raise PreventUpdate
        
        global df_para
        df_table = pd.DataFrame(
            {
                'para_name': df_para.columns[1:],
                'para_value': df_para.loc[current_ref][1:]
            }
        )
        table = dash_table.DataTable(
            data=df_table.to_dict('records'),
            style_cell={'textAlign': 'left'},
            style_cell_conditional=[
                {'if': {'column_id': 'para_name'}, 'textAlign': 'left', 'fontWeight': 'bold'},
                {'if': {'column_id': 'para_value'}, 'textAlign': 'right'},
            ],
            style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'},
        )
        return [table]


    app.run(debug=True)
    pass

if __name__ == "__main__":
    bt_result_file_names = get_bt_result_file_name('HSI')
    df_bt_result_list = [read_csv_with_metadata(file_name) for file_name in bt_result_file_names]
    plot_app(df_bt_result_list)

