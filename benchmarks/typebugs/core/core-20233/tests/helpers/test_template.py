"""Test Home Assistant template helper methods."""
import asyncio
from datetime import datetime
import unittest
import random
import math
import pytz
from unittest.mock import patch

from homeassistant.components import group
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import template
from homeassistant.util.unit_system import UnitSystem
from homeassistant.const import (
    LENGTH_METERS,
    TEMP_CELSIUS,
    MASS_GRAMS,
    VOLUME_LITERS,
    MATCH_ALL,
)
import homeassistant.util.dt as dt_util

from tests.common import get_test_home_assistant
import pytest


class TestHelpersTemplate(unittest.TestCase):
    """Test the Template."""

    # pylint: disable=invalid-name
    def setUp(self):
        """Set up the tests."""
        self.hass = get_test_home_assistant()
        self.hass.config.units = UnitSystem('custom', TEMP_CELSIUS,
                                            LENGTH_METERS, VOLUME_LITERS,
                                            MASS_GRAMS)

    # pylint: disable=invalid-name
    def tearDown(self):
        """Stop down stuff we started."""
        self.hass.stop()

    def test_referring_states_by_entity_id(self):
        """Test referring states by entity id."""
        self.hass.states.set('test.object', 'happy')
        assert 'happy' == \
            template.Template(
                '{{ states.test.object.state }}', self.hass).render()

    def test_iterating_all_states(self):
        """Test iterating all states."""
        self.hass.states.set('test.object', 'happy')
        self.hass.states.set('sensor.temperature', 10)

        assert '10happy' == \
            template.Template(
                '{% for state in states %}{{ state.state }}{% endfor %}',
                self.hass).render()

    def test_iterating_domain_states(self):
        """Test iterating domain states."""
        self.hass.states.set('test.object', 'happy')
        self.hass.states.set('sensor.back_door', 'open')
        self.hass.states.set('sensor.temperature', 10)

        assert 'open10' == \
            template.Template("""
{% for state in states.sensor %}{{ state.state }}{% endfor %}
                """, self.hass).render()

    def test_float(self):
        """Test float."""
        self.hass.states.set('sensor.temperature', '12')

        assert '12.0' == \
            template.Template(
                '{{ float(states.sensor.temperature.state) }}',
                self.hass).render()

        assert 'True' == \
            template.Template(
                '{{ float(states.sensor.temperature.state) > 11 }}',
                self.hass).render()

    def test_rounding_value(self):
        """Test rounding value."""
        self.hass.states.set('sensor.temperature', 12.78)

        assert '12.8' == \
            template.Template(
                '{{ states.sensor.temperature.state | round(1) }}',
                self.hass).render()

        assert '128' == \
            template.Template(
                '{{ states.sensor.temperature.state | multiply(10) | round }}',
                self.hass).render()

    def test_rounding_value_get_original_value_on_error(self):
        """Test rounding value get original value on error."""
        assert 'None' == \
            template.Template('{{ None | round }}', self.hass).render()

        assert 'no_number' == \
            template.Template(
                '{{ "no_number" | round }}', self.hass).render()

    def test_multiply(self):
        """Test multiply."""
        tests = {
            None: 'None',
            10: '100',
            '"abcd"': 'abcd'
        }

        for inp, out in tests.items():
            assert out == \
                template.Template('{{ %s | multiply(10) | round }}' % inp,
                                  self.hass).render()

    def test_logarithm(self):
        """Test logarithm."""
        tests = [
            (4, 2, '2.0'),
            (1000, 10, '3.0'),
            (math.e, '', '1.0'),
            ('"invalid"', '_', 'invalid'),
            (10, '"invalid"', '10.0'),
        ]

        for value, base, expected in tests:
            assert expected == \
                template.Template(
                    '{{ %s | log(%s) | round(1) }}' % (value, base),
                    self.hass).render()

            assert expected == \
                template.Template(
                    '{{ log(%s, %s) | round(1) }}' % (value, base),
                    self.hass).render()

    def test_sine(self):
        """Test sine."""
        tests = [
            (0, '0.0'),
            (math.pi / 2, '1.0'),
            (math.pi, '0.0'),
            (math.pi * 1.5, '-1.0'),
            (math.pi / 10, '0.309')
        ]

        for value, expected in tests:
            assert expected == \
                template.Template(
                    '{{ %s | sin | round(3) }}' % value,
                    self.hass).render()

    def test_cos(self):
        """Test cosine."""
        tests = [
            (0, '1.0'),
            (math.pi / 2, '0.0'),
            (math.pi, '-1.0'),
            (math.pi * 1.5, '-0.0'),
            (math.pi / 10, '0.951')
        ]

        for value, expected in tests:
            assert expected == \
                template.Template(
                    '{{ %s | cos | round(3) }}' % value,
                    self.hass).render()

    def test_tan(self):
        """Test tangent."""
        tests = [
            (0, '0.0'),
            (math.pi, '-0.0'),
            (math.pi / 180 * 45, '1.0'),
            (math.pi / 180 * 90, '1.633123935319537e+16'),
            (math.pi / 180 * 135, '-1.0')
        ]

        for value, expected in tests:
            assert expected == \
                template.Template(
                    '{{ %s | tan | round(3) }}' % value,
                    self.hass).render()

    def test_sqrt(self):
        """Test square root."""
        tests = [
            (0, '0.0'),
            (1, '1.0'),
            (2, '1.414'),
            (10, '3.162'),
            (100, '10.0'),
        ]

        for value, expected in tests:
            assert expected == \
                template.Template(
                    '{{ %s | sqrt | round(3) }}' % value,
                    self.hass).render()

    def test_strptime(self):
        """Test the parse timestamp method."""
        tests = [
            ('2016-10-19 15:22:05.588122 UTC',
             '%Y-%m-%d %H:%M:%S.%f %Z', None),
            ('2016-10-19 15:22:05.588122+0100',
             '%Y-%m-%d %H:%M:%S.%f%z', None),
            ('2016-10-19 15:22:05.588122',
             '%Y-%m-%d %H:%M:%S.%f', None),
            ('2016-10-19', '%Y-%m-%d', None),
            ('2016', '%Y', None),
            ('15:22:05', '%H:%M:%S', None),
            ('1469119144', '%Y', '1469119144'),
            ('invalid', '%Y', 'invalid')
        ]

        for inp, fmt, expected in tests:
            if expected is None:
                expected = datetime.strptime(inp, fmt)

            temp = '{{ strptime(\'%s\', \'%s\') }}' % (inp, fmt)

            assert str(expected) == \
                template.Template(temp, self.hass).render()

    def test_timestamp_custom(self):
        """Test the timestamps to custom filter."""
        now = dt_util.utcnow()
        tests = [
            (None, None, None, 'None'),
            (1469119144, None, True, '2016-07-21 16:39:04'),
            (1469119144, '%Y', True, '2016'),
            (1469119144, 'invalid', True, 'invalid'),
            (dt_util.as_timestamp(now), None, False,
                now.strftime('%Y-%m-%d %H:%M:%S'))
        ]

        for inp, fmt, local, out in tests:
            if fmt:
                fil = 'timestamp_custom(\'{}\')'.format(fmt)
            elif fmt and local:
                fil = 'timestamp_custom(\'{0}\', {1})'.format(fmt, local)
            else:
                fil = 'timestamp_custom'

            assert out == template.Template(
                '{{ %s | %s }}' % (inp, fil), self.hass).render()

    def test_timestamp_local(self):
        """Test the timestamps to local filter."""
        tests = {
            None: 'None',
            1469119144: '2016-07-21 16:39:04',
        }

        for inp, out in tests.items():
            assert out == \
                template.Template('{{ %s | timestamp_local }}' % inp,
                                  self.hass).render()

    def test_min(self):
        """Test the min filter."""
        assert '1' == \
            template.Template('{{ [1, 2, 3] | min }}',
                              self.hass).render()

    def test_max(self):
        """Test the max filter."""
        assert '3' == \
            template.Template('{{ [1, 2, 3] | max }}',
                              self.hass).render()

    def test_base64_encode(self):
        """Test the base64_encode filter."""
        self.assertEqual(
            'aG9tZWFzc2lzdGFudA==',
            template.Template('{{ "homeassistant" | base64_encode }}',
                              self.hass).render())

    def test_base64_decode(self):
        """Test the base64_decode filter."""
        self.assertEqual(
            'homeassistant',
            template.Template('{{ "aG9tZWFzc2lzdGFudA==" | base64_decode }}',
                              self.hass).render())

    def test_ordinal(self):
        """Test the ordinal filter."""
        tests = [
            (1, '1st'),
            (2, '2nd'),
            (3, '3rd'),
            (4, '4th'),
            (5, '5th'),
        ]

        for value, expected in tests:
            self.assertEqual(
                expected,
                template.Template(
                    '{{ %s | ordinal }}' % value,
                    self.hass).render())

    def test_timestamp_utc(self):
        """Test the timestamps to local filter."""
        now = dt_util.utcnow()
        tests = {
            None: 'None',
            1469119144: '2016-07-21 16:39:04',
            dt_util.as_timestamp(now):
                now.strftime('%Y-%m-%d %H:%M:%S')
        }

        for inp, out in tests.items():
            assert out == \
                template.Template('{{ %s | timestamp_utc }}' % inp,
                                  self.hass).render()

    def test_as_timestamp(self):
        """Test the as_timestamp function."""
        assert "None" == \
            template.Template(
                '{{ as_timestamp("invalid") }}', self.hass).render()
        self.hass.mock = None
        assert "None" == \
            template.Template('{{ as_timestamp(states.mock) }}',
                              self.hass).render()

        tpl = '{{ as_timestamp(strptime("2024-02-03T09:10:24+0000", ' \
            '"%Y-%m-%dT%H:%M:%S%z")) }}'
        assert "1706951424.0" == \
            template.Template(tpl, self.hass).render()

    @patch.object(random, 'choice')
    def test_random_every_time(self, test_choice):
        """Ensure the random filter runs every time, not just once."""
        tpl = template.Template('{{ [1,2] | random }}', self.hass)
        test_choice.return_value = 'foo'
        assert 'foo' == tpl.render()
        test_choice.return_value = 'bar'
        assert 'bar' == tpl.render()

    def test_passing_vars_as_keywords(self):
        """Test passing variables as keywords."""
        assert '127' == \
            template.Template('{{ hello }}', self.hass).render(hello=127)

    def test_passing_vars_as_vars(self):
        """Test passing variables as variables."""
        assert '127' == \
            template.Template('{{ hello }}', self.hass).render({'hello': 127})

    def test_passing_vars_as_list(self):
        """Test passing variables as list."""
        assert "['foo', 'bar']" == \
            template.render_complex(template.Template('{{ hello }}',
                                    self.hass), {'hello': ['foo', 'bar']})

    def test_passing_vars_as_list_element(self):
        """Test passing variables as list."""
        assert 'bar' == \
            template.render_complex(template.Template('{{ hello[1] }}',
                                    self.hass),
                                    {'hello': ['foo', 'bar']})

    def test_passing_vars_as_dict_element(self):
        """Test passing variables as list."""
        assert 'bar' == \
            template.render_complex(template.Template('{{ hello.foo }}',
                                    self.hass),
                                    {'hello': {'foo': 'bar'}})

    def test_passing_vars_as_dict(self):
        """Test passing variables as list."""
        assert "{'foo': 'bar'}" == \
            template.render_complex(template.Template('{{ hello }}',
                                    self.hass), {'hello': {'foo': 'bar'}})

    def test_render_with_possible_json_value_with_valid_json(self):
        """Render with possible JSON value with valid JSON."""
        tpl = template.Template('{{ value_json.hello }}', self.hass)
        assert 'world' == \
            tpl.render_with_possible_json_value('{"hello": "world"}')

    def test_render_with_possible_json_value_with_invalid_json(self):
        """Render with possible JSON value with invalid JSON."""
        tpl = template.Template('{{ value_json }}', self.hass)
        assert '' == \
            tpl.render_with_possible_json_value('{ I AM NOT JSON }')

    def test_render_with_possible_json_value_with_template_error_value(self):
        """Render with possible JSON value with template error value."""
        tpl = template.Template('{{ non_existing.variable }}', self.hass)
        assert '-' == \
            tpl.render_with_possible_json_value('hello', '-')

    def test_render_with_possible_json_value_with_missing_json_value(self):
        """Render with possible JSON value with unknown JSON object."""
        tpl = template.Template('{{ value_json.goodbye }}', self.hass)
        assert '' == \
            tpl.render_with_possible_json_value('{"hello": "world"}')

    def test_render_with_possible_json_value_valid_with_is_defined(self):
        """Render with possible JSON value with known JSON object."""
        tpl = template.Template('{{ value_json.hello|is_defined }}', self.hass)
        assert 'world' == \
            tpl.render_with_possible_json_value('{"hello": "world"}')

    def test_render_with_possible_json_value_undefined_json(self):
        """Render with possible JSON value with unknown JSON object."""
        tpl = template.Template('{{ value_json.bye|is_defined }}', self.hass)
        assert '{"hello": "world"}' == \
            tpl.render_with_possible_json_value('{"hello": "world"}')

    def test_render_with_possible_json_value_undefined_json_error_value(self):
        """Render with possible JSON value with unknown JSON object."""
        tpl = template.Template('{{ value_json.bye|is_defined }}', self.hass)
        assert '' == \
            tpl.render_with_possible_json_value('{"hello": "world"}', '')

    def test_render_with_possible_json_value_non_string_value(self):
        """Render with possible JSON value with non-string value."""
        tpl = template.Template("""
{{ strptime(value~'+0000', '%Y-%m-%d %H:%M:%S%z') }}
            """, self.hass)
        value = datetime(2019, 1, 18, 12, 13, 14)
        expected = str(pytz.utc.localize(value))
        assert expected == \
            tpl.render_with_possible_json_value(value)

    def test_render_with_possible_json_value_non_string_value_noassert(self):
        """Render with possible JSON value with non-string value."""
        tpl = template.Template("""
{{ strptime(value~'+0000', '%Y-%m-%d %H:%M:%S%z') }}
            """, self.hass)
        value = datetime(2019, 1, 18, 12, 13, 14)
        expected = str(pytz.utc.localize(value))
        expected == \
            tpl.render_with_possible_json_value(value)

    def test_raise_exception_on_error(self):
        """Test raising an exception on error."""
        with pytest.raises(TemplateError):
            template.Template('{{ invalid_syntax').ensure_valid()

    def test_if_state_exists(self):
        """Test if state exists works."""
        self.hass.states.set('test.object', 'available')
        tpl = template.Template(
            '{% if states.test.object %}exists{% else %}not exists{% endif %}',
            self.hass)
        assert 'exists' == tpl.render()

    def test_is_state(self):
        """Test is_state method."""
        self.hass.states.set('test.object', 'available')
        tpl = template.Template("""
{% if is_state("test.object", "available") %}yes{% else %}no{% endif %}
            """, self.hass)
        assert 'yes' == tpl.render()

        tpl = template.Template("""
{{ is_state("test.noobject", "available") }}
            """, self.hass)
        assert 'False' == tpl.render()

    def test_is_state_attr(self):
        """Test is_state_attr method."""
        self.hass.states.set('test.object', 'available', {'mode': 'on'})
        tpl = template.Template("""
{% if is_state_attr("test.object", "mode", "on") %}yes{% else %}no{% endif %}
                """, self.hass)
        assert 'yes' == tpl.render()

        tpl = template.Template("""
{{ is_state_attr("test.noobject", "mode", "on") }}
                """, self.hass)
        assert 'False' == tpl.render()

    def test_state_attr(self):
        """Test state_attr method."""
        self.hass.states.set('test.object', 'available', {'mode': 'on'})
        tpl = template.Template("""
{% if state_attr("test.object", "mode") == "on" %}yes{% else %}no{% endif %}
                """, self.hass)
        assert 'yes' == tpl.render()

        tpl = template.Template("""
{{ state_attr("test.noobject", "mode") == None }}
                """, self.hass)
        assert 'True' == tpl.render()

    def test_states_function(self):
        """Test using states as a function."""
        self.hass.states.set('test.object', 'available')
        tpl = template.Template('{{ states("test.object") }}', self.hass)
        assert 'available' == tpl.render()

        tpl2 = template.Template('{{ states("test.object2") }}', self.hass)
        assert 'unknown' == tpl2.render()

    @patch('homeassistant.helpers.template.TemplateEnvironment.'
           'is_safe_callable', return_value=True)
    def test_now(self, mock_is_safe):
        """Test now method."""
        now = dt_util.now()
        with patch.dict(template.ENV.globals, {'now': lambda: now}):
            assert now.isoformat() == \
                template.Template('{{ now().isoformat() }}',
                                  self.hass).render()

    @patch('homeassistant.helpers.template.TemplateEnvironment.'
           'is_safe_callable', return_value=True)
    def test_utcnow(self, mock_is_safe):
        """Test utcnow method."""
        now = dt_util.utcnow()
        with patch.dict(template.ENV.globals, {'utcnow': lambda: now}):
            assert now.isoformat() == \
                template.Template('{{ utcnow().isoformat() }}',
                                  self.hass).render()

    def test_regex_match(self):
        """Test regex_match method."""
        tpl = template.Template(r"""
{{ '123-456-7890' | regex_match('(\\d{3})-(\\d{3})-(\\d{4})') }}
                """, self.hass)
        assert 'True' == tpl.render()

        tpl = template.Template("""
{{ 'home assistant test' | regex_match('Home', True) }}
                """, self.hass)
        assert 'True' == tpl.render()

        tpl = template.Template("""
        {{ 'Another home assistant test' | regex_match('home') }}
                        """, self.hass)
        assert 'False' == tpl.render()

    def test_regex_search(self):
        """Test regex_search method."""
        tpl = template.Template(r"""
{{ '123-456-7890' | regex_search('(\\d{3})-(\\d{3})-(\\d{4})') }}
                """, self.hass)
        assert 'True' == tpl.render()

        tpl = template.Template("""
{{ 'home assistant test' | regex_search('Home', True) }}
                """, self.hass)
        assert 'True' == tpl.render()

        tpl = template.Template("""
        {{ 'Another home assistant test' | regex_search('home') }}
                        """, self.hass)
        assert 'True' == tpl.render()

    def test_regex_replace(self):
        """Test regex_replace method."""
        tpl = template.Template(r"""
{{ 'Hello World' | regex_replace('(Hello\\s)',) }}
                """, self.hass)
        assert 'World' == tpl.render()

    def test_regex_findall_index(self):
        """Test regex_findall_index method."""
        tpl = template.Template("""
{{ 'Flight from JFK to LHR' | regex_findall_index('([A-Z]{3})', 0) }}
                """, self.hass)
        assert 'JFK' == tpl.render()

        tpl = template.Template("""
{{ 'Flight from JFK to LHR' | regex_findall_index('([A-Z]{3})', 1) }}
                """, self.hass)
        assert 'LHR' == tpl.render()

    def test_bitwise_and(self):
        """Test bitwise_and method."""
        tpl = template.Template("""
{{ 8 | bitwise_and(8) }}
                """, self.hass)
        assert str(8 & 8) == tpl.render()
        tpl = template.Template("""
{{ 10 | bitwise_and(2) }}
                """, self.hass)
        assert str(10 & 2) == tpl.render()
        tpl = template.Template("""
{{ 8 | bitwise_and(2) }}
                """, self.hass)
        assert str(8 & 2) == tpl.render()

    def test_bitwise_or(self):
        """Test bitwise_or method."""
        tpl = template.Template("""
{{ 8 | bitwise_or(8) }}
                """, self.hass)
        assert str(8 | 8) == tpl.render()
        tpl = template.Template("""
{{ 10 | bitwise_or(2) }}
                """, self.hass)
        assert str(10 | 2) == tpl.render()
        tpl = template.Template("""
{{ 8 | bitwise_or(2) }}
                """, self.hass)
        assert str(8 | 2) == tpl.render()

    def test_distance_function_with_1_state(self):
        """Test distance function with 1 state."""
        self.hass.states.set('test.object', 'happy', {
            'latitude': 32.87336,
            'longitude': -117.22943,
        })
        tpl = template.Template('{{ distance(states.test.object) | round }}',
                                self.hass)
        assert '187' == tpl.render()

    def test_distance_function_with_2_states(self):
        """Test distance function with 2 states."""
        self.hass.states.set('test.object', 'happy', {
            'latitude': 32.87336,
            'longitude': -117.22943,
        })
        self.hass.states.set('test.object_2', 'happy', {
            'latitude': self.hass.config.latitude,
            'longitude': self.hass.config.longitude,
        })
        tpl = template.Template(
            '{{ distance(states.test.object, states.test.object_2) | round }}',
            self.hass)
        assert '187' == tpl.render()

    def test_distance_function_with_1_coord(self):
        """Test distance function with 1 coord."""
        tpl = template.Template(
            '{{ distance("32.87336", "-117.22943") | round }}', self.hass)
        assert '187' == \
            tpl.render()

    def test_distance_function_with_2_coords(self):
        """Test distance function with 2 coords."""
        assert '187' == \
            template.Template(
                '{{ distance("32.87336", "-117.22943", %s, %s) | round }}'
                % (self.hass.config.latitude, self.hass.config.longitude),
                self.hass).render()

    def test_distance_function_with_1_state_1_coord(self):
        """Test distance function with 1 state 1 coord."""
        self.hass.states.set('test.object_2', 'happy', {
            'latitude': self.hass.config.latitude,
            'longitude': self.hass.config.longitude,
        })
        tpl = template.Template(
            '{{ distance("32.87336", "-117.22943", states.test.object_2) '
            '| round }}', self.hass)
        assert '187' == tpl.render()

        tpl2 = template.Template(
            '{{ distance(states.test.object_2, "32.87336", "-117.22943") '
            '| round }}', self.hass)
        assert '187' == tpl2.render()

    def test_distance_function_return_None_if_invalid_state(self):
        """Test distance function return None if invalid state."""
        self.hass.states.set('test.object_2', 'happy', {
            'latitude': 10,
        })
        tpl = template.Template('{{ distance(states.test.object_2) | round }}',
                                self.hass)
        assert 'None' == \
            tpl.render()

    def test_distance_function_return_None_if_invalid_coord(self):
        """Test distance function return None if invalid coord."""
        assert 'None' == \
            template.Template(
                '{{ distance("123", "abc") }}', self.hass).render()

        assert 'None' == \
            template.Template('{{ distance("123") }}', self.hass).render()

        self.hass.states.set('test.object_2', 'happy', {
            'latitude': self.hass.config.latitude,
            'longitude': self.hass.config.longitude,
        })
        tpl = template.Template('{{ distance("123", states.test_object_2) }}',
                                self.hass)
        assert 'None' == \
            tpl.render()

    def test_distance_function_with_2_entity_ids(self):
        """Test distance function with 2 entity ids."""
        self.hass.states.set('test.object', 'happy', {
            'latitude': 32.87336,
            'longitude': -117.22943,
        })
        self.hass.states.set('test.object_2', 'happy', {
            'latitude': self.hass.config.latitude,
            'longitude': self.hass.config.longitude,
        })
        tpl = template.Template(
            '{{ distance("test.object", "test.object_2") | round }}',
            self.hass)
        assert '187' == tpl.render()

    def test_distance_function_with_1_entity_1_coord(self):
        """Test distance function with 1 entity_id and 1 coord."""
        self.hass.states.set('test.object', 'happy', {
            'latitude': self.hass.config.latitude,
            'longitude': self.hass.config.longitude,
        })
        tpl = template.Template(
            '{{ distance("test.object", "32.87336", "-117.22943") | round }}',
            self.hass)
        assert '187' == tpl.render()

    def test_closest_function_home_vs_domain(self):
        """Test closest function home vs domain."""
        self.hass.states.set('test_domain.object', 'happy', {
            'latitude': self.hass.config.latitude + 0.1,
            'longitude': self.hass.config.longitude + 0.1,
        })

        self.hass.states.set('not_test_domain.but_closer', 'happy', {
            'latitude': self.hass.config.latitude,
            'longitude': self.hass.config.longitude,
        })

        assert 'test_domain.object' == \
            template.Template('{{ closest(states.test_domain).entity_id }}',
                              self.hass).render()

    def test_closest_function_home_vs_all_states(self):
        """Test closest function home vs all states."""
        self.hass.states.set('test_domain.object', 'happy', {
            'latitude': self.hass.config.latitude + 0.1,
            'longitude': self.hass.config.longitude + 0.1,
        })

        self.hass.states.set('test_domain_2.and_closer', 'happy', {
            'latitude': self.hass.config.latitude,
            'longitude': self.hass.config.longitude,
        })

        assert 'test_domain_2.and_closer' == \
            template.Template('{{ closest(states).entity_id }}',
                              self.hass).render()

    def test_closest_function_home_vs_group_entity_id(self):
        """Test closest function home vs group entity id."""
        self.hass.states.set('test_domain.object', 'happy', {
            'latitude': self.hass.config.latitude + 0.1,
            'longitude': self.hass.config.longitude + 0.1,
        })

        self.hass.states.set('not_in_group.but_closer', 'happy', {
            'latitude': self.hass.config.latitude,
            'longitude': self.hass.config.longitude,
        })

        group.Group.create_group(
            self.hass, 'location group', ['test_domain.object'])

        assert 'test_domain.object' == \
            template.Template(
                '{{ closest("group.location_group").entity_id }}',
                self.hass).render()

    def test_closest_function_home_vs_group_state(self):
        """Test closest function home vs group state."""
        self.hass.states.set('test_domain.object', 'happy', {
            'latitude': self.hass.config.latitude + 0.1,
            'longitude': self.hass.config.longitude + 0.1,
        })

        self.hass.states.set('not_in_group.but_closer', 'happy', {
            'latitude': self.hass.config.latitude,
            'longitude': self.hass.config.longitude,
        })

        group.Group.create_group(
            self.hass, 'location group', ['test_domain.object'])

        assert 'test_domain.object' == \
            template.Template(
                '{{ closest(states.group.location_group).entity_id }}',
                self.hass).render()

    def test_closest_function_to_coord(self):
        """Test closest function to coord."""
        self.hass.states.set('test_domain.closest_home', 'happy', {
            'latitude': self.hass.config.latitude + 0.1,
            'longitude': self.hass.config.longitude + 0.1,
        })

        self.hass.states.set('test_domain.closest_zone', 'happy', {
            'latitude': self.hass.config.latitude + 0.2,
            'longitude': self.hass.config.longitude + 0.2,
        })

        self.hass.states.set('zone.far_away', 'zoning', {
            'latitude': self.hass.config.latitude + 0.3,
            'longitude': self.hass.config.longitude + 0.3,
        })

        tpl = template.Template(
            '{{ closest("%s", %s, states.test_domain).entity_id }}'
            % (self.hass.config.latitude + 0.3,
               self.hass.config.longitude + 0.3), self.hass)

        assert 'test_domain.closest_zone' == \
            tpl.render()

    def test_closest_function_to_entity_id(self):
        """Test closest function to entity id."""
        self.hass.states.set('test_domain.closest_home', 'happy', {
            'latitude': self.hass.config.latitude + 0.1,
            'longitude': self.hass.config.longitude + 0.1,
        })

        self.hass.states.set('test_domain.closest_zone', 'happy', {
            'latitude': self.hass.config.latitude + 0.2,
            'longitude': self.hass.config.longitude + 0.2,
        })

        self.hass.states.set('zone.far_away', 'zoning', {
            'latitude': self.hass.config.latitude + 0.3,
            'longitude': self.hass.config.longitude + 0.3,
        })

        assert 'test_domain.closest_zone' == \
            template.Template(
                '{{ closest("zone.far_away", '
                'states.test_domain).entity_id }}', self.hass).render()

    def test_closest_function_to_state(self):
        """Test closest function to state."""
        self.hass.states.set('test_domain.closest_home', 'happy', {
            'latitude': self.hass.config.latitude + 0.1,
            'longitude': self.hass.config.longitude + 0.1,
        })

        self.hass.states.set('test_domain.closest_zone', 'happy', {
            'latitude': self.hass.config.latitude + 0.2,
            'longitude': self.hass.config.longitude + 0.2,
        })

        self.hass.states.set('zone.far_away', 'zoning', {
            'latitude': self.hass.config.latitude + 0.3,
            'longitude': self.hass.config.longitude + 0.3,
        })

        assert 'test_domain.closest_zone' == \
            template.Template(
                '{{ closest(states.zone.far_away, '
                'states.test_domain).entity_id }}', self.hass).render()

    def test_closest_function_invalid_state(self):
        """Test closest function invalid state."""
        self.hass.states.set('test_domain.closest_home', 'happy', {
            'latitude': self.hass.config.latitude + 0.1,
            'longitude': self.hass.config.longitude + 0.1,
        })

        for state in ('states.zone.non_existing', '"zone.non_existing"'):
            assert 'None' == \
                template.Template('{{ closest(%s, states) }}' % state,
                                  self.hass).render()

    def test_closest_function_state_with_invalid_location(self):
        """Test closest function state with invalid location."""
        self.hass.states.set('test_domain.closest_home', 'happy', {
            'latitude': 'invalid latitude',
            'longitude': self.hass.config.longitude + 0.1,
        })

        assert 'None' == \
            template.Template(
                '{{ closest(states.test_domain.closest_home, '
                'states) }}', self.hass).render()

    def test_closest_function_invalid_coordinates(self):
        """Test closest function invalid coordinates."""
        self.hass.states.set('test_domain.closest_home', 'happy', {
            'latitude': self.hass.config.latitude + 0.1,
            'longitude': self.hass.config.longitude + 0.1,
        })

        assert 'None' == \
            template.Template('{{ closest("invalid", "coord", states) }}',
                              self.hass).render()

    def test_closest_function_no_location_states(self):
        """Test closest function without location states."""
        assert '' == \
            template.Template('{{ closest(states).entity_id }}',
                              self.hass).render()

    def test_extract_entities_none_exclude_stuff(self):
        """Test extract entities function with none or exclude stuff."""
        assert [] == template.extract_entities(None)

        assert [] == template.extract_entities("mdi:water")

        assert MATCH_ALL == \
            template.extract_entities(
                '{{ closest(states.zone.far_away, '
                'states.test_domain).entity_id }}')

        assert MATCH_ALL == \
            template.extract_entities(
                '{{ distance("123", states.test_object_2) }}')

    def test_extract_entities_no_match_entities(self):
        """Test extract entities function with none entities stuff."""
        assert MATCH_ALL == \
            template.extract_entities(
                "{{ value_json.tst | timestamp_custom('%Y' True) }}")

        assert MATCH_ALL == \
            template.extract_entities("""
{% for state in states.sensor %}
  {{ state.entity_id }}={{ state.state }},d
{% endfor %}
            """)

    def test_extract_entities_match_entities(self):
        """Test extract entities function with entities stuff."""
        assert ['device_tracker.phone_1'] == \
            template.extract_entities("""
{% if is_state('device_tracker.phone_1', 'home') %}
    Ha, Hercules is home!
{% else %}
    Hercules is at {{ states('device_tracker.phone_1') }}.
{% endif %}
            """)

        assert ['binary_sensor.garage_door'] == \
            template.extract_entities("""
{{ as_timestamp(states.binary_sensor.garage_door.last_changed) }}
            """)

        assert ['binary_sensor.garage_door'] == \
            template.extract_entities("""
{{ states("binary_sensor.garage_door") }}
            """)

        assert ['device_tracker.phone_2'] == \
            template.extract_entities("""
{{ is_state_attr('device_tracker.phone_2', 'battery', 40) }}
            """)

        assert sorted([
                'device_tracker.phone_1',
                'device_tracker.phone_2',
            ]) == \
            sorted(template.extract_entities("""
{% if is_state('device_tracker.phone_1', 'home') %}
    Ha, Hercules is home!
{% elif states.device_tracker.phone_2.attributes.battery < 40 %}
    Hercules you power goes done!.
{% endif %}
            """))

        assert sorted([
                'sensor.pick_humidity',
                'sensor.pick_temperature',
            ]) == \
            sorted(template.extract_entities("""
{{
    states.sensor.pick_temperature.state ~ „°C (“ ~
    states.sensor.pick_humidity.state ~ „ %“
}}
            """))

        assert sorted([
                'sensor.luftfeuchtigkeit_mean',
                'input_number.luftfeuchtigkeit',
            ]) == \
            sorted(template.extract_entities(
                "{% if (states('sensor.luftfeuchtigkeit_mean') | int)"
                " > (states('input_number.luftfeuchtigkeit') | int +1.5)"
                " %}true{% endif %}"
            ))

    def test_extract_entities_with_variables(self):
        """Test extract entities function with variables and entities stuff."""
        assert ['input_boolean.switch'] == \
            template.extract_entities(
                "{{ is_state('input_boolean.switch', 'off') }}", {})

        assert ['trigger.entity_id'] == \
            template.extract_entities(
                "{{ is_state(trigger.entity_id, 'off') }}", {})

        assert MATCH_ALL == \
            template.extract_entities(
                "{{ is_state(data, 'off') }}", {})

        assert ['input_boolean.switch'] == \
            template.extract_entities(
                "{{ is_state(data, 'off') }}",
                {'data': 'input_boolean.switch'})

        assert ['input_boolean.switch'] == \
            template.extract_entities(
                "{{ is_state(trigger.entity_id, 'off') }}",
                {'trigger': {'entity_id': 'input_boolean.switch'}})

        assert MATCH_ALL == \
            template.extract_entities(
                "{{ is_state('media_player.' ~ where , 'playing') }}",
                {'where': 'livingroom'})

    def test_jinja_namespace(self):
        """Test Jinja's namespace command can be used."""
        test_template = template.Template(
            (
                "{% set ns = namespace(a_key='') %}"
                "{% set ns.a_key = states.sensor.dummy.state %}"
                "{{ ns.a_key }}"
            ),
            self.hass
        )

        self.hass.states.set('sensor.dummy', 'a value')
        assert 'a value' == test_template.render()

        self.hass.states.set('sensor.dummy', 'another value')
        assert 'another value' == test_template.render()


@asyncio.coroutine
def test_state_with_unit(hass):
    """Test the state_with_unit property helper."""
    hass.states.async_set('sensor.test', '23', {
        'unit_of_measurement': 'beers',
    })
    hass.states.async_set('sensor.test2', 'wow')

    tpl = template.Template(
        '{{ states.sensor.test.state_with_unit }}', hass)

    assert tpl.async_render() == '23 beers'

    tpl = template.Template(
        '{{ states.sensor.test2.state_with_unit }}', hass)

    assert tpl.async_render() == 'wow'

    tpl = template.Template(
        '{% for state in states %}{{ state.state_with_unit }} {% endfor %}',
        hass)

    assert tpl.async_render() == '23 beers wow'

    tpl = template.Template('{{ states.sensor.non_existing.state_with_unit }}',
                            hass)

    assert tpl.async_render() == ''


@asyncio.coroutine
def test_length_of_states(hass):
    """Test fetching the length of states."""
    hass.states.async_set('sensor.test', '23')
    hass.states.async_set('sensor.test2', 'wow')
    hass.states.async_set('climate.test2', 'cooling')

    tpl = template.Template('{{ states | length }}', hass)
    assert tpl.async_render() == '3'

    tpl = template.Template('{{ states.sensor | length }}', hass)
    assert tpl.async_render() == '2'
