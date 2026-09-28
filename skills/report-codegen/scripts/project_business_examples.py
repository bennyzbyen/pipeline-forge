"""Synthetic project examples, not default business rules or production adapters."""
from decimal import Decimal


def o2o_sku(row, date, *, version, confirmed):
    if confirmed is not True or version not in {'historical_or', 'working_date_ne_d'}:
        raise ValueError('O2O version must be explicitly adopted')
    date_match = row.get('date') == date
    if version == 'working_date_ne_d':
        # Mongo $ne matches missing fields as well. Do not replace with dropna().
        return date_match and row.get('data_type') != 'D'
    if 'data_type' not in row:
        raise ValueError('historical post-query filter requires data_type column')
    old_or = all(row.get(k) == '1' for k in ('is_create', 'is_exist', 'is_onsale', 'is_quantity')) or row.get('is_sold') == '1'
    return date_match and old_or and row['data_type'] != 'D'


def grade(gsv, periods):
    # Historical example uses Python round, not DTR HALF_UP.
    average = round(gsv / periods, 2) if periods else 0
    return average, 'high' if average >= 130 else 'qualified' if average >= 60 else 'low'


def geography_join(details, dimensions, keys, *, missing):
    import pandas as pd
    if missing not in {'error', 'degraded'} or not keys:
        raise ValueError('join key and missing policy required')
    unique = dimensions.drop_duplicates()
    if unique[keys].isna().any().any() or unique.duplicated(keys).any():
        raise ValueError('ambiguous geography key; selection rule required')
    result = details.merge(unique, on=keys, how='left', validate='many_to_one', indicator=True)
    if missing == 'error' and (result['_merge'] == 'left_only').any():
        raise ValueError('missing geography mapping')
    result['mapping_status'] = result['_merge'].map({'both': 'matched', 'left_only': 'degraded', 'right_only': 'unused'})
    return result.drop(columns='_merge')


def target_achievement(actual, target, keys):
    # q3 example: inner join, null accuracy defaults to 1; absent column is an error.
    required = keys + ['sku_count_target', 'acuracy_rate']
    selected = target[required].dropna(subset=['sku_count_target'])
    if selected.duplicated(keys).any():
        raise ValueError('duplicate target grain')
    result = actual.merge(selected, on=keys, how='inner', validate='many_to_one')
    result['achievement_rate'] = (result['actual'] / result['sku_count_target'] * result['acuracy_rate'].fillna(1)).clip(upper=1.1).round(4)
    return result


def rebuild_rollup(filtered_details, keys):
    # Only for explicitly additive targets; distinct targets require their own contract.
    return filtered_details.groupby(keys, as_index=False)[['actual', 'sku_count_target']].sum()


def dsd_store_days(frame, start, end):
    selected = frame.loc[frame['order_day'].between(start, end)]
    days = selected.groupby(['store_id', 'order_day'], as_index=False)['gsv'].sum()
    return days.groupby('store_id', as_index=False).agg(purchase_days=('order_day', 'count'), gsv=('gsv', 'sum'))


def dtr_quantity(row, *, kind, eo_actual_types):
    status = str(row['status'])
    if kind == 'sales':
        field = {'4508': 'delivered', '4': 'delivered', '4506': 'shipped', '4516': 'partial'}.get(status, 'ordered')
        return Decimal(0) if status in {'4509', '5'} else row[field]
    if kind != 'return':
        raise ValueError('sales/return contract required')
    if row.get('source') == 'EO订单' and row.get('interconnect') in eo_actual_types:
        return row['ordered']
    if status in {'4', '4505', '已取消'}:
        return Decimal(0)
    field = 'stored' if status in {'3', '4504', '已完成'} else 'received' if status in {'2', '4503', '待入库'} else 'ordered'
    return row[field]
