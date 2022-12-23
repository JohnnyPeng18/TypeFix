# -*- coding: utf-8 -*-
# Arithmetc tests for DataFrame/Series/Index/Array classes that should
# behave identically.
# Specifically for object dtype
import operator

import pytest
import numpy as np

import pandas as pd
import pandas.util.testing as tm
from pandas.core import ops

from pandas import Series, Timestamp


# ------------------------------------------------------------------
# Comparisons

class TestObjectComparisons(object):

    def test_comparison_object_numeric_nas(self):
        ser = Series(np.random.randn(10), dtype=object)
        shifted = ser.shift(2)

        ops = ['lt', 'le', 'gt', 'ge', 'eq', 'ne']
        for op in ops:
            func = getattr(operator, op)

            result = func(ser, shifted)
            expected = func(ser.astype(float), shifted.astype(float))
            tm.assert_series_equal(result, expected)

    def test_object_comparisons(self):
        ser = Series(['a', 'b', np.nan, 'c', 'a'])

        result = ser == 'a'
        expected = Series([True, False, False, False, True])
        tm.assert_series_equal(result, expected)

        result = ser < 'a'
        expected = Series([False, False, False, False, False])
        tm.assert_series_equal(result, expected)

        result = ser != 'a'
        expected = -(ser == 'a')
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize('dtype', [None, object])
    def test_more_na_comparisons(self, dtype):
        left = Series(['a', np.nan, 'c'], dtype=dtype)
        right = Series(['a', np.nan, 'd'], dtype=dtype)

        result = left == right
        expected = Series([True, False, False])
        tm.assert_series_equal(result, expected)

        result = left != right
        expected = Series([False, True, True])
        tm.assert_series_equal(result, expected)

        result = left == np.nan
        expected = Series([False, False, False])
        tm.assert_series_equal(result, expected)

        result = left != np.nan
        expected = Series([True, True, True])
        tm.assert_series_equal(result, expected)


# ------------------------------------------------------------------
# Arithmetic

class TestArithmetic(object):
    @pytest.mark.parametrize("op", [operator.add, ops.radd])
    @pytest.mark.parametrize("other", ["category", "Int64"])
    def test_pos_add_extension_scalar(self, other, box_pos, op):
        # GH#22378
        # Check that scalars satisfying is_extension_array_dtype(obj)
        # do not incorrectly try to dispatch to an ExtensionArray operation
        arr = pd.Series(['a', 'b', 'c'])
        expected = pd.Series([op(x, other) for x in arr])

        arr = tm.box_expected(arr, box_pos)
        expected = tm.box_expected(expected, box_pos)

        result = op(arr, other)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize("op", [operator.add, ops.radd])
    @pytest.mark.parametrize("other", ["category", "Int64"])
    def test_add_extension_scalar(self, other, box_neg, op):
        # GH#22378
        # Check that scalars satisfying is_extension_array_dtype(obj)
        # do not incorrectly try to dispatch to an ExtensionArray operation
        arr = pd.Series(['a', 'b', 'c'])
        expected = pd.Series([op(x, other) for x in arr])

        arr = tm.box_expected(arr, box_neg)
        expected = tm.box_expected(expected, box_neg)

        result = op(arr, other)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize('box', [
        pytest.param(pd.Index,
                     marks=pytest.mark.xfail(reason="Does not mask nulls",
                                             strict=True, raises=TypeError)),
        pd.Series,
        pd.DataFrame
    ], ids=lambda x: x.__name__)
    def test_objarr_add_str(self, box):
        ser = pd.Series(['x', np.nan, 'x'])
        expected = pd.Series(['xa', np.nan, 'xa'])

        ser = tm.box_expected(ser, box)
        expected = tm.box_expected(expected, box)

        result = ser + 'a'
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize('box', [
        pytest.param(pd.Index,
                     marks=pytest.mark.xfail(reason="Does not mask nulls",
                                             strict=True, raises=TypeError)),
        pd.Series,
        pd.DataFrame
    ], ids=lambda x: x.__name__)
    def test_objarr_radd_str(self, box):
        ser = pd.Series(['x', np.nan, 'x'])
        expected = pd.Series(['ax', np.nan, 'ax'])

        ser = tm.box_expected(ser, box)
        expected = tm.box_expected(expected, box)

        result = 'a' + ser
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize('data', [
        [1, 2, 3],
        [1.1, 2.2, 3.3],
        [Timestamp('2011-01-01'), Timestamp('2011-01-02'), pd.NaT],
        ['x', 'y', 1]])
    @pytest.mark.parametrize('dtype', [None, object])
    def test_objarr_radd_str_invalid(self, dtype, data, box):
        ser = Series(data, dtype=dtype)

        ser = tm.box_expected(ser, box)
        with pytest.raises(TypeError):
            'foo_' + ser

    @pytest.mark.parametrize('op', [operator.add, ops.radd,
                                    operator.sub, ops.rsub])
    def test_objarr_add_invalid(self, op, box):
        # invalid ops
        if box is pd.DataFrame and op is ops.radd:
            pytest.xfail(reason="DataFrame op incorrectly casts the np.array"
                                "case to M8[ns]")

        obj_ser = tm.makeObjectSeries()
        obj_ser.name = 'objects'

        obj_ser = tm.box_expected(obj_ser, box)
        with pytest.raises(Exception):
            op(obj_ser, 1)
        with pytest.raises(Exception):
            op(obj_ser, np.array(1, dtype=np.int64))

    # TODO: Moved from tests.series.test_operators; needs cleanup
    def test_operators_na_handling(self):
        ser = Series(['foo', 'bar', 'baz', np.nan])
        result = 'prefix_' + ser
        expected = pd.Series(['prefix_foo', 'prefix_bar',
                              'prefix_baz', np.nan])
        tm.assert_series_equal(result, expected)

        result = ser + '_suffix'
        expected = pd.Series(['foo_suffix', 'bar_suffix',
                              'baz_suffix', np.nan])
        tm.assert_series_equal(result, expected)

    # TODO: parametrize over box
    @pytest.mark.parametrize('dtype', [None, object])
    def test_series_with_dtype_radd_timedelta(self, dtype):
        # note this test is _not_ aimed at timedelta64-dtyped Series
        ser = pd.Series([pd.Timedelta('1 days'), pd.Timedelta('2 days'),
                         pd.Timedelta('3 days')], dtype=dtype)
        expected = pd.Series([pd.Timedelta('4 days'), pd.Timedelta('5 days'),
                              pd.Timedelta('6 days')])

        result = pd.Timedelta('3 days') + ser
        tm.assert_series_equal(result, expected)

        result = ser + pd.Timedelta('3 days')
        tm.assert_series_equal(result, expected)
