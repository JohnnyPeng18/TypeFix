"""Template helper methods for rendering strings with Home Assistant data."""
from datetime import datetime
import json
import logging
import math
import random
import base64
import re

import jinja2
from jinja2 import contextfilter
from jinja2.sandbox import ImmutableSandboxedEnvironment
from jinja2.utils import Namespace

from homeassistant.const import (
    ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_UNIT_OF_MEASUREMENT, MATCH_ALL,
    STATE_UNKNOWN)
from homeassistant.core import State, valid_entity_id
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import location as loc_helper
from homeassistant.helpers.typing import TemplateVarsType
from homeassistant.loader import bind_hass
from homeassistant.util import convert
from homeassistant.util import dt as dt_util
from homeassistant.util import location as loc_util
from homeassistant.util.async_ import run_callback_threadsafe

_LOGGER = logging.getLogger(__name__)
_SENTINEL = object()
DATE_STR_FORMAT = "%Y-%m-%d %H:%M:%S"

_RE_NONE_ENTITIES = re.compile(r"distance\(|closest\(", re.I | re.M)
_RE_GET_ENTITIES = re.compile(
    r"(?:(?:states\.|(?:is_state|is_state_attr|state_attr|states)"
    r"\((?:[\ \'\"]?))([\w]+\.[\w]+)|([\w]+))", re.I | re.M
)
_RE_JINJA_DELIMITERS = re.compile(r"\{%|\{\{")


@bind_hass
def attach(hass, obj):
    """Recursively attach hass to all template instances in list and dict."""
    if isinstance(obj, list):
        for child in obj:
            attach(hass, child)
    elif isinstance(obj, dict):
        for child in obj.values():
            attach(hass, child)
    elif isinstance(obj, Template):
        obj.hass = hass


def render_complex(value, variables=None):
    """Recursive template creator helper function."""
    if isinstance(value, list):
        return [render_complex(item, variables)
                for item in value]
    if isinstance(value, dict):
        return {key: render_complex(item, variables)
                for key, item in value.items()}
    return value.async_render(variables)


def extract_entities(template, variables=None):
    """Extract all entities for state_changed listener from template string."""
    if template is None or _RE_JINJA_DELIMITERS.search(template) is None:
        return []

    if _RE_NONE_ENTITIES.search(template):
        return MATCH_ALL

    extraction = _RE_GET_ENTITIES.findall(template)
    extraction_final = []

    for result in extraction:
        if result[0] == 'trigger.entity_id' and 'trigger' in variables and \
           'entity_id' in variables['trigger']:
            extraction_final.append(variables['trigger']['entity_id'])
        elif result[0]:
            extraction_final.append(result[0])

        if variables and result[1] in variables and \
           isinstance(variables[result[1]], str) and \
           valid_entity_id(variables[result[1]]):
            extraction_final.append(variables[result[1]])

    if extraction_final:
        return list(set(extraction_final))
    return MATCH_ALL


class Template:
    """Class to hold a template and manage caching and rendering."""

    def __init__(self, template, hass=None):
        """Instantiate a template."""
        if not isinstance(template, str):
            raise TypeError('Expected template to be a string')

        self.template = template
        self._compiled_code = None
        self._compiled = None
        self.hass = hass

    def ensure_valid(self):
        """Return if template is valid."""
        if self._compiled_code is not None:
            return

        try:
            self._compiled_code = ENV.compile(self.template)
        except jinja2.exceptions.TemplateSyntaxError as err:
            raise TemplateError(err)

    def extract_entities(self, variables=None):
        """Extract all entities for state_changed listener."""
        return extract_entities(self.template, variables)

    def render(self, variables: TemplateVarsType = None, **kwargs):
        """Render given template."""
        if variables is not None:
            kwargs.update(variables)

        return run_callback_threadsafe(
            self.hass.loop, self.async_render, kwargs).result()

    def async_render(self, variables: TemplateVarsType = None,
                     **kwargs) -> str:
        """Render given template.

        This method must be run in the event loop.
        """
        if self._compiled is None:
            self._ensure_compiled()

        if variables is not None:
            kwargs.update(variables)

        try:
            return self._compiled.render(kwargs).strip()
        except jinja2.TemplateError as err:
            raise TemplateError(err)

    def render_with_possible_json_value(self, value, error_value=_SENTINEL):
        """Render template with value exposed.

        If valid JSON will expose value_json too.
        """
        return run_callback_threadsafe(
            self.hass.loop, self.async_render_with_possible_json_value, value,
            error_value).result()

    def async_render_with_possible_json_value(self, value,
                                              error_value=_SENTINEL,
                                              variables=None):
        """Render template with value exposed.

        If valid JSON will expose value_json too.

        This method must be run in the event loop.
        """
        if self._compiled is None:
            self._ensure_compiled()

        variables = dict(variables or {})
        variables['value'] = value

        try:
            variables['value_json'] = json.loads(value)
        except (ValueError, TypeError):
            pass

        try:
            return self._compiled.render(variables).strip()
        except jinja2.TemplateError as ex:
            if error_value is _SENTINEL:
                _LOGGER.error(
                    "Error parsing value: %s (value: %s, template: %s)",
                    ex, value, self.template)
            return value if error_value is _SENTINEL else error_value

    def _ensure_compiled(self):
        """Bind a template to a specific hass instance."""
        self.ensure_valid()

        assert self.hass is not None, 'hass variable not set on template'

        template_methods = TemplateMethods(self.hass)

        global_vars = ENV.make_globals({
            'closest': template_methods.closest,
            'distance': template_methods.distance,
            'is_state': self.hass.states.is_state,
            'is_state_attr': template_methods.is_state_attr,
            'state_attr': template_methods.state_attr,
            'states': AllStates(self.hass),
        })

        self._compiled = jinja2.Template.from_code(
            ENV, self._compiled_code, global_vars, None)

        return self._compiled

    def __eq__(self, other):
        """Compare template with another."""
        return (self.__class__ == other.__class__ and
                self.template == other.template and
                self.hass == other.hass)


class AllStates:
    """Class to expose all HA states as attributes."""

    def __init__(self, hass):
        """Initialize all states."""
        self._hass = hass

    def __getattr__(self, name):
        """Return the domain state."""
        return DomainStates(self._hass, name)

    def __iter__(self):
        """Return all states."""
        return iter(
            _wrap_state(state) for state in
            sorted(self._hass.states.async_all(),
                   key=lambda state: state.entity_id))

    def __len__(self):
        """Return number of states."""
        return len(self._hass.states.async_entity_ids())

    def __call__(self, entity_id):
        """Return the states."""
        state = self._hass.states.get(entity_id)
        return STATE_UNKNOWN if state is None else state.state


class DomainStates:
    """Class to expose a specific HA domain as attributes."""

    def __init__(self, hass, domain):
        """Initialize the domain states."""
        self._hass = hass
        self._domain = domain

    def __getattr__(self, name):
        """Return the states."""
        return _wrap_state(
            self._hass.states.get('{}.{}'.format(self._domain, name)))

    def __iter__(self):
        """Return the iteration over all the states."""
        return iter(sorted(
            (_wrap_state(state) for state in self._hass.states.async_all()
             if state.domain == self._domain),
            key=lambda state: state.entity_id))

    def __len__(self):
        """Return number of states."""
        return len(self._hass.states.async_entity_ids(self._domain))


class TemplateState(State):
    """Class to represent a state object in a template."""

    # Inheritance is done so functions that check against State keep working
    # pylint: disable=super-init-not-called
    def __init__(self, state):
        """Initialize template state."""
        self._state = state

    @property
    def state_with_unit(self):
        """Return the state concatenated with the unit if available."""
        state = object.__getattribute__(self, '_state')
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit is None:
            return state.state
        return "{} {}".format(state.state, unit)

    def __getattribute__(self, name):
        """Return an attribute of the state."""
        if name in TemplateState.__dict__:
            return object.__getattribute__(self, name)
        return getattr(object.__getattribute__(self, '_state'), name)

    def __repr__(self):
        """Representation of Template State."""
        rep = object.__getattribute__(self, '_state').__repr__()
        return '<template ' + rep[1:]


def _wrap_state(state):
    """Wrap a state."""
    return None if state is None else TemplateState(state)


class TemplateMethods:
    """Class to expose helpers to templates."""

    def __init__(self, hass):
        """Initialize the helpers."""
        self._hass = hass

    def closest(self, *args):
        """Find closest entity.

        Closest to home:
          closest(states)
          closest(states.device_tracker)
          closest('group.children')
          closest(states.group.children)

        Closest to a point:
          closest(23.456, 23.456, 'group.children')
          closest('zone.school', 'group.children')
          closest(states.zone.school, 'group.children')
        """
        if len(args) == 1:
            latitude = self._hass.config.latitude
            longitude = self._hass.config.longitude
            entities = args[0]

        elif len(args) == 2:
            point_state = self._resolve_state(args[0])

            if point_state is None:
                _LOGGER.warning("Closest:Unable to find state %s", args[0])
                return None
            if not loc_helper.has_location(point_state):
                _LOGGER.warning(
                    "Closest:State does not contain valid location: %s",
                    point_state)
                return None

            latitude = point_state.attributes.get(ATTR_LATITUDE)
            longitude = point_state.attributes.get(ATTR_LONGITUDE)

            entities = args[1]

        else:
            latitude = convert(args[0], float)
            longitude = convert(args[1], float)

            if latitude is None or longitude is None:
                _LOGGER.warning(
                    "Closest:Received invalid coordinates: %s, %s",
                    args[0], args[1])
                return None

            entities = args[2]

        if isinstance(entities, (AllStates, DomainStates)):
            states = list(entities)
        else:
            if isinstance(entities, State):
                gr_entity_id = entities.entity_id
            else:
                gr_entity_id = str(entities)

            group = self._hass.components.group

            states = [self._hass.states.get(entity_id) for entity_id
                      in group.expand_entity_ids([gr_entity_id])]

        return _wrap_state(loc_helper.closest(latitude, longitude, states))

    def distance(self, *args):
        """Calculate distance.

        Will calculate distance from home to a point or between points.
        Points can be passed in using state objects or lat/lng coordinates.
        """
        locations = []

        to_process = list(args)

        while to_process:
            value = to_process.pop(0)
            point_state = self._resolve_state(value)

            if point_state is None:
                # We expect this and next value to be lat&lng
                if not to_process:
                    _LOGGER.warning(
                        "Distance:Expected latitude and longitude, got %s",
                        value)
                    return None

                value_2 = to_process.pop(0)
                latitude = convert(value, float)
                longitude = convert(value_2, float)

                if latitude is None or longitude is None:
                    _LOGGER.warning("Distance:Unable to process latitude and "
                                    "longitude: %s, %s", value, value_2)
                    return None

            else:
                if not loc_helper.has_location(point_state):
                    _LOGGER.warning(
                        "distance:State does not contain valid location: %s",
                        point_state)
                    return None

                latitude = point_state.attributes.get(ATTR_LATITUDE)
                longitude = point_state.attributes.get(ATTR_LONGITUDE)

                if latitude is None or longitude is None:
                    _LOGGER.warning(
                        "Distance:State does not contains a location: %s",
                        value)
                    return None

            locations.append((latitude, longitude))

        if len(locations) == 1:
            return self._hass.config.distance(*locations[0])

        return self._hass.config.units.length(
            loc_util.distance(*locations[0] + locations[1]), 'm')

    def is_state_attr(self, entity_id, name, value):
        """Test if a state is a specific attribute."""
        state_attr = self.state_attr(entity_id, name)
        return state_attr is not None and state_attr == value

    def state_attr(self, entity_id, name):
        """Get a specific attribute from a state."""
        state_obj = self._hass.states.get(entity_id)
        if state_obj is not None:
            return state_obj.attributes.get(name)
        return None

    def _resolve_state(self, entity_id_or_state):
        """Return state or entity_id if given."""
        if isinstance(entity_id_or_state, State):
            return entity_id_or_state
        if isinstance(entity_id_or_state, str):
            return self._hass.states.get(entity_id_or_state)
        return None


def forgiving_round(value, precision=0):
    """Round accepted strings."""
    try:
        value = round(float(value), precision)
        return int(value) if precision == 0 else value
    except (ValueError, TypeError):
        # If value can't be converted to float
        return value


def multiply(value, amount):
    """Filter to convert value to float and multiply it."""
    try:
        return float(value) * amount
    except (ValueError, TypeError):
        # If value can't be converted to float
        return value


def logarithm(value, base=math.e):
    """Filter to get logarithm of the value with a specific base."""
    try:
        return math.log(float(value), float(base))
    except (ValueError, TypeError):
        return value


def sine(value):
    """Filter to get sine of the value."""
    try:
        return math.sin(float(value))
    except (ValueError, TypeError):
        return value


def cosine(value):
    """Filter to get cosine of the value."""
    try:
        return math.cos(float(value))
    except (ValueError, TypeError):
        return value


def tangent(value):
    """Filter to get tangent of the value."""
    try:
        return math.tan(float(value))
    except (ValueError, TypeError):
        return value


def square_root(value):
    """Filter to get square root of the value."""
    try:
        return math.sqrt(float(value))
    except (ValueError, TypeError):
        return value


def timestamp_custom(value, date_format=DATE_STR_FORMAT, local=True):
    """Filter to convert given timestamp to format."""
    try:
        date = dt_util.utc_from_timestamp(value)

        if local:
            date = dt_util.as_local(date)

        return date.strftime(date_format)
    except (ValueError, TypeError):
        # If timestamp can't be converted
        return value


def timestamp_local(value):
    """Filter to convert given timestamp to local date/time."""
    try:
        return dt_util.as_local(
            dt_util.utc_from_timestamp(value)).strftime(DATE_STR_FORMAT)
    except (ValueError, TypeError):
        # If timestamp can't be converted
        return value


def timestamp_utc(value):
    """Filter to convert given timestamp to UTC date/time."""
    try:
        return dt_util.utc_from_timestamp(value).strftime(DATE_STR_FORMAT)
    except (ValueError, TypeError):
        # If timestamp can't be converted
        return value


def forgiving_as_timestamp(value):
    """Try to convert value to timestamp."""
    try:
        return dt_util.as_timestamp(value)
    except (ValueError, TypeError):
        return None


def strptime(string, fmt):
    """Parse a time string to datetime."""
    try:
        return datetime.strptime(string, fmt)
    except (ValueError, AttributeError):
        return string


def fail_when_undefined(value):
    """Filter to force a failure when the value is undefined."""
    if isinstance(value, jinja2.Undefined):
        value()
    return value


def forgiving_float(value):
    """Try to convert value to a float."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return value


def regex_match(value, find='', ignorecase=False):
    """Match value using regex."""
    if not isinstance(value, str):
        value = str(value)
    flags = re.I if ignorecase else 0
    return bool(re.match(find, value, flags))


def regex_replace(value='', find='', replace='', ignorecase=False):
    """Replace using regex."""
    if not isinstance(value, str):
        value = str(value)
    flags = re.I if ignorecase else 0
    regex = re.compile(find, flags)
    return regex.sub(replace, value)


def regex_search(value, find='', ignorecase=False):
    """Search using regex."""
    if not isinstance(value, str):
        value = str(value)
    flags = re.I if ignorecase else 0
    return bool(re.search(find, value, flags))


def regex_findall_index(value, find='', index=0, ignorecase=False):
    """Find all matches using regex and then pick specific match index."""
    if not isinstance(value, str):
        value = str(value)
    flags = re.I if ignorecase else 0
    return re.findall(find, value, flags)[index]


def bitwise_and(first_value, second_value):
    """Perform a bitwise and operation."""
    return first_value & second_value


def bitwise_or(first_value, second_value):
    """Perform a bitwise or operation."""
    return first_value | second_value


def base64_encode(value):
    """Perform base64 encode."""
    return base64.b64encode(value.encode('utf-8')).decode('utf-8')


def base64_decode(value):
    """Perform base64 denode."""
    return base64.b64decode(value).decode('utf-8')


def ordinal(value):
    """Perform ordinal conversion."""
    return str(value) + (list(['th', 'st', 'nd', 'rd'] + ['th'] * 6)
                         [(int(str(value)[-1])) % 10] if
                         int(str(value)[-2:]) % 100 not in range(11, 14)
                         else 'th')


@contextfilter
def random_every_time(context, values):
    """Choose a random value.

    Unlike Jinja's random filter,
    this is context-dependent to avoid caching the chosen value.
    """
    return random.choice(values)


class TemplateEnvironment(ImmutableSandboxedEnvironment):
    """The Home Assistant template environment."""

    def is_safe_callable(self, obj):
        """Test if callback is safe."""
        return isinstance(obj, AllStates) or super().is_safe_callable(obj)

    def is_safe_attribute(self, obj, attr, value):
        """Test if attribute is safe."""
        return isinstance(obj, Namespace) or \
            super().is_safe_attribute(obj, attr, value)


ENV = TemplateEnvironment()
ENV.filters['round'] = forgiving_round
ENV.filters['multiply'] = multiply
ENV.filters['log'] = logarithm
ENV.filters['sin'] = sine
ENV.filters['cos'] = cosine
ENV.filters['tan'] = tangent
ENV.filters['sqrt'] = square_root
ENV.filters['timestamp_custom'] = timestamp_custom
ENV.filters['timestamp_local'] = timestamp_local
ENV.filters['timestamp_utc'] = timestamp_utc
ENV.filters['is_defined'] = fail_when_undefined
ENV.filters['max'] = max
ENV.filters['min'] = min
ENV.filters['random'] = random_every_time
ENV.filters['base64_encode'] = base64_encode
ENV.filters['base64_decode'] = base64_decode
ENV.filters['ordinal'] = ordinal
ENV.filters['regex_match'] = regex_match
ENV.filters['regex_replace'] = regex_replace
ENV.filters['regex_search'] = regex_search
ENV.filters['regex_findall_index'] = regex_findall_index
ENV.filters['bitwise_and'] = bitwise_and
ENV.filters['bitwise_or'] = bitwise_or
ENV.globals['log'] = logarithm
ENV.globals['sin'] = sine
ENV.globals['cos'] = cosine
ENV.globals['tan'] = tangent
ENV.globals['sqrt'] = square_root
ENV.globals['pi'] = math.pi
ENV.globals['tau'] = math.pi * 2
ENV.globals['e'] = math.e
ENV.globals['float'] = forgiving_float
ENV.globals['now'] = dt_util.now
ENV.globals['utcnow'] = dt_util.utcnow
ENV.globals['as_timestamp'] = forgiving_as_timestamp
ENV.globals['relative_time'] = dt_util.get_age
ENV.globals['strptime'] = strptime
