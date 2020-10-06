import pytest
from tri_declarative import (
    Namespace,
    Refinable,
    class_shortcut,
)
from tri_struct import Struct

from iommi import (
    Column,
    Field,
    Form,
    Fragment,
    Table, register_style, Style, MenuItem, Menu,
)
from iommi.base import (
    items,
    keys,
)
from iommi.page import (
    Page,
)
from iommi.style import unregister_style
from iommi.traversable import (
    build_long_path_by_path,
    EvaluatedRefinable,
    reinvokable,
    Traversable,
    evaluated_refinable,
)
from tests.helpers import (
    req,
    StubTraversable,
)
from tests.models import TFoo


def test_traverse():
    bar = Struct(
        _name='bar',
        _declared_members=dict(
            baz=Struct(_name='baz'),
            buzz=Struct(_name='buzz'),
        ),
    )
    foo = Struct(
        _name='foo',
        _declared_members=dict(
            bar=bar,
        ),
    )
    root = StubTraversable(
        _name='root',
        members=Struct(
            foo=foo
        ),
    )

    expected = {
        '': '',
        'foo': 'foo',
        'bar': 'foo/bar',
        'baz': 'foo/bar/baz',
        'buzz': 'foo/bar/buzz',
    }
    actual = build_long_path_by_path(root)
    assert items(actual) == items(expected)
    assert len(keys(actual)) == len(set(keys(actual)))


@pytest.mark.django_db
def test_traverse_on_iommi():
    class MyPage(Page):
        header = Fragment()
        some_form = Form(fields=Namespace(
            fisk=Field(),
        ))
        some_other_form = Form(fields=Namespace(
            fjomp=Field(),
            fisk=Field(),
        ))
        a_table = Table(
            model=TFoo,
            columns=Namespace(
                columns=Column(),
                fusk=Column(attr='b', filter__include=True),
            ),
        )

    page = MyPage(_name='root')

    actual = build_long_path_by_path(page)
    assert len(actual.keys()) == len(set(actual.keys()))
    page = page.bind(request=req('get'))

    assert page.iommi_path == ''
    assert page.parts.header.iommi_path == 'header'
    assert page.parts.some_form.fields.fisk.iommi_path == 'fisk'
    assert page.parts.some_other_form.fields.fisk.iommi_path == 'some_other_form/fisk'
    assert page.parts.a_table.query.form.iommi_path == 'form'
    assert page.parts.a_table.query.form.fields.fusk.iommi_path == 'fusk'
    assert page.parts.a_table.columns.fusk.iommi_path == 'a_table/fusk'


def test_evil_names_that_work():
    class EvilPage(Page):
        name = Fragment()
        parent = Fragment()
        path = Fragment()

    assert EvilPage().bind(request=req('get')).render_to_response().status_code == 200


def test_evil_names():
    class ErrorMessages(Page):
        bind = Fragment()
        iommi_style = Fragment()
        iommi_path = Fragment()
        iommi_dunderpath = Fragment()
        on_bind = Fragment()
        own_evaluate_parameters = Fragment()
        get_request = Fragment()

    with pytest.raises(Exception) as e:
        ErrorMessages()

    assert str(e.value) == 'The names bind, get_request, iommi_path, iommi_style, on_bind, own_evaluate_parameters are reserved by iommi, please pick other names'


def test_dunder_path_is_fully_qualified_and_skipping_root():
    foo = StubTraversable(
        _name='my_part3',
        members=Struct(
            my_part2=StubTraversable(
                _name='my_part2',
                members=Struct(
                    my_part=StubTraversable(
                        _name='my_part',
                    )
                )
            )
        )
    )
    foo = foo.bind(request=None)

    assert foo.iommi_path == ''

    assert foo.iommi_bound_members().my_part2.iommi_path == 'my_part2'
    assert foo.iommi_bound_members().my_part2.iommi_dunder_path == 'my_part2'

    assert foo.iommi_bound_members().my_part2.iommi_bound_members().my_part.iommi_path == 'my_part'
    assert foo.iommi_bound_members().my_part2.iommi_bound_members().my_part.iommi_dunder_path == 'my_part2__my_part'


class MyReinvokable(Traversable):
    @reinvokable
    def __init__(self, **kwargs):
        self.kwargs = Struct(kwargs)


def test_reinvokable():
    x = MyReinvokable(foo=17)
    x = x.reinvoke(dict(bar=42))
    assert x.kwargs == dict(foo=17, bar=42)


def test_reinvokable_cache_is_respected():
    x = MyReinvokable(foo=17)
    x._iommi_saved_params == dict(foo=17)
    x._iommi_saved_params['foo'] = 42
    x = x.reinvoke(dict(bar=42))
    assert x.kwargs == dict(foo=42, bar=42)


def test_reinvokable_recurse():
    x = MyReinvokable(foo=MyReinvokable(bar=17))
    x = x.reinvoke(Namespace(foo__bar=42))

    assert isinstance(x.kwargs.foo, MyReinvokable)
    assert x.kwargs.foo.kwargs == dict(bar=42)


def test_reinvoke_namespace_merge():
    class ReinvokableWithExtra(Traversable):
        extra = Refinable()

        @reinvokable
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

    assert ReinvokableWithExtra(
        extra__foo=17
    ).reinvoke(Namespace(
        extra__bar=42
    )).extra == dict(bar=42, foo=17)

    # Try again with pre-Namespaced kwargs
    assert ReinvokableWithExtra(
        **Namespace(extra__foo=17)
    ).reinvoke(Namespace(
        extra__bar=42
    )).extra == dict(bar=42, foo=17)


def test_reinvokable_recurse_retain_original():
    x = MyReinvokable(
        a=1,
        foo=MyReinvokable(
            b=2,
            bar=MyReinvokable(
                c=3,
                baz=17
            )
        )
    )
    x = x.reinvoke(Namespace(foo__bar__baz=42))

    assert isinstance(x.kwargs.foo, MyReinvokable)
    assert x.kwargs.a == 1
    assert x.kwargs.foo.kwargs.b == 2
    assert x.kwargs.foo.kwargs.bar.kwargs.c == 3
    assert x.kwargs.foo.kwargs.bar.kwargs.baz == 42


def test_reinvoke_path():
    class MyForm(Form):
        my_field = Field.choice(
            choices=[],
        )

    my_form = MyForm(
        fields__my_field__choices=[1, 2, 3],
    )

    assert my_form.bind().fields.my_field.choices == [1, 2, 3]


def test_reinvoke_dicts():
    class MyForm(Form):
        my_field = Field.choice(
            choices=[],
        )

    my_form = MyForm(
        fields=dict(
            my_field=dict(
                choices=[1, 2, 3],
            ),
        ),
    )

    assert my_form.bind().fields.my_field.choices == [1, 2, 3]


def test_reinvoke_extra():
    class MyForm(Form):
        my_field = Field(
            extra__foo=17,
        )

    f = MyForm(
        fields__my_field__extra__bar=42
    )

    assert f.bind().fields.my_field.extra == dict(foo=17, bar=42)


def test_reinvoke_extra_shortcut():
    class MyField(Field):
        @classmethod
        @class_shortcut(
            extra__buz=4711,
        )
        def shortcut(cls, call_target, **kwargs):
            return call_target(**kwargs)

    class MyForm(Form):
        my_field = MyField.shortcut(
            extra__foo=17,
        )

    f = MyForm(
        fields__my_field__extra__bar=42
    )

    assert f.bind().fields.my_field.extra == dict(foo=17, bar=42, buz=4711)


def test_evaluated_refinable_function():
    class Foo(Traversable):
        @staticmethod
        @evaluated_refinable
        def foo(**_):
            return 1

    f = Foo().bind(request=None)
    assert f.foo == 1


def test_extra_evaluated():
    class Foo(Traversable):
        extra_evaluated = Refinable()

        def own_evaluate_parameters(self):
            return dict(x=3)

    f = Foo(extra_evaluated__foo=lambda x, **_: x).bind(request=None)
    assert f.extra_evaluated.foo == 3


def test_attrs_evaluated():
    class Foo(Traversable):
        attrs = Refinable()

        def own_evaluate_parameters(self):
            return dict(x=3)

    f = Foo(attrs__foo=lambda x, **_: x).bind(request=None)
    assert f.attrs.foo == 3


def test_instance_in_eval_args():
    class Foo(Traversable):
        bar = EvaluatedRefinable()

    f = Foo(bar=lambda traversable, **_: traversable).bind(request=None)
    assert f.bar == f


def test_initial_setup():
    t = Traversable()
    assert t.iommi_name() is None
    assert t.iommi_parent() is None
    assert t._is_bound is False
    assert t.get_request() is None
    assert t.iommi_evaluate_parameters() is None


def test_traversable_repr():

    bar = StubTraversable(_name='bar')
    foo = StubTraversable(
        _name='foo',
        members=Struct(
            bar=bar,
        ),
    )

    assert repr(foo) == '<tests.helpers.StubTraversable foo>'
    assert repr(bar) == '<tests.helpers.StubTraversable bar>'

    foo = foo.bind(request=None)

    assert repr(foo) == "<tests.helpers.StubTraversable foo (bound) members:['bar']>"
    assert repr(foo._bound_members.bar) == "<tests.helpers.StubTraversable bar (bound) path:'bar'>"


@pytest.mark.skip('Fails due to styles beeing applied too soon')
def test_apply_style_not_affecting_definition(settings):
    register_style('my_style', Style(
        Fragment__attrs__class__foo=True,
    ))

    register_style('other_style', Style(
        Fragment__attrs__class__bar=True,
    ))

    definition = Fragment()

    settings.IOMMI_DEFAULT_STYLE = 'my_style'
    fragment = definition.bind(request=None)
    assert fragment.attrs['class'] == dict(foo=True)

    settings.IOMMI_DEFAULT_STYLE = 'other_style'
    fragment = definition.bind(request=None)
    assert fragment.attrs['class'] == dict(bar=True)

    unregister_style('my_style')
    unregister_style('other_style')


@pytest.mark.skip('Fails due to styles beeing applied too soon')
def test_apply_style_not_affecting_definition_2():
    register_style('foo_style', Style(
        MenuItem__attrs__class__foo=True,
    ))

    register_style('bar_style', Style(
        MenuItem__attrs__class__bar=True,
    ))

    class MyPage(Page):
        menu = Menu(
            sub_menu=dict(
                root=MenuItem()
            )
        )

    class OtherPage(Page):
        menu = MyPage.menu

    page = MyPage(iommi_style='foo_style').bind(request=Struct(path=''))
    assert page.parts.menu.sub_menu.root.attrs['class'] == dict(foo=True)

    page = OtherPage(iommi_style='bar_style').bind(request=Struct(path=''))
    assert page.parts.menu.sub_menu.root.attrs['class'] == dict(bar=True)

    unregister_style('foo_style')
    unregister_style('bar_style')
