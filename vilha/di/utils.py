import inspect
from typing import (
    Annotated,
    Any,
    Callable,
    Dict,
    ForwardRef,
    List,
    get_args,
    get_origin,
)
from starlette.concurrency import run_in_threadpool
from vilha.di.datastructures import Dependant, Depends


def is_coroutine_callable(call: Callable[..., Any]) -> bool:
    if inspect.isroutine(call):
        return inspect.iscoroutinefunction(call)
    if inspect.isclass(call):
        return False
    dunder_call = getattr(call, "__call__", None)  # noqa: B004
    return inspect.iscoroutinefunction(dunder_call)


def get_typed_signature(call: Callable[..., Any]) -> inspect.Signature:
    signature = inspect.signature(call)
    globalns = getattr(call, "__globals__", {})
    typed_params = [
        inspect.Parameter(
            name=param.name,
            kind=param.kind,
            default=param.default,
            annotation=get_typed_annotation(param.annotation, globalns),
        )
        for param in signature.parameters.values()
    ]
    typed_signature = inspect.Signature(typed_params)
    return typed_signature


def get_typed_annotation(annotation: Any, globalns: Dict[str, Any]) -> Any:
    if isinstance(annotation, str):
        annotation = ForwardRef(annotation)
        # annotation = evaluate_forwardref(annotation, globalns, globalns)
        annotation = annotation._evaluate(globalns, globalns, frozenset())
    return annotation


def get_typed_return_annotation(call: Callable[..., Any]) -> Any:
    signature = inspect.signature(call)
    annotation = signature.return_annotation

    if annotation is inspect.Signature.empty:
        return None

    globalns = getattr(call, "__globals__", {})
    return get_typed_annotation(annotation, globalns)


def get_dependant(*, call: Callable[..., Any], name: str):
    endpoint_signature = get_typed_signature(call)
    signature_params = endpoint_signature.parameters
    dependant = Dependant(call=call, name=name)

    for param_name, param in signature_params.items():
        type_annotation, depends = analyze_param(
            param_name=param_name, annotation=param.annotation, value=param.default
        )
        print(f"Param name {param_name}")
        print(f"Type annotation {type_annotation}")
        print(f"Depends {depends}")
        if depends is not None:
            sub_dependant = get_dependant(call=depends.dependency, name=param_name)
            dependant.dependencies.append(sub_dependant)
            continue
        else:
            sub_dependant = Dependant(name=param_name)
            dependant.dependencies.append(sub_dependant)
            continue

    return dependant


def analyze_param(*, param_name: str, annotation: Any, value: Any):
    # field_info = None
    depends = None
    type_annotation: Any = Any
    use_annotation: Any = Any

    if annotation is not inspect.Signature.empty:
        type_annotation = annotation
        use_annotation = annotation
        print(f"Use Annotation {use_annotation}")
    if get_origin(use_annotation) is Annotated:
        annotated_args = get_args(use_annotation)
        type_annotation = annotated_args[0]

        annotations = [arg for arg in annotated_args[1:] if isinstance(arg, Depends)]

        print(f"Annotations {annotations}")
        if annotations:
            annotation = annotations[-1]
        else:
            annotation = None
        depends = annotation

    if isinstance(value, Depends):
        assert depends is None, (
            "Cannot specify `Depends` in `Annotated` and default value",
            f" together for {param_name!r}",
        )

        depends = value

    if depends is not None and depends.dependency is None:
        depends.dependency = type_annotation

    return type_annotation, depends


async def solve_by_name(*, dependant: Dependant, ctx: Dict[str, Any] = {}):
    values = {}
    errors = []
    supports = False
    if dependant.call is None and dependant.name is not None:
        supports = True
        name = dependant.name
        solved = ctx.get(name)
        if solved is None:
            errors.append(f"{name} could not be solved")
        values[name] = solved
    return values, errors, supports


async def solve_by_call(*, dependant: Dependant, ctx: Dict[str, Any] = {}):
    values = {}
    errors = []
    supports = False
    if dependant.call is not None and dependant.name is not None:
        supports = True
        call = dependant.call
        name = dependant.name
        solved_result = await solve_dependencies(dependant=dependant, ctx=ctx)
        (sub_values, sub_errors) = solved_result
        if sub_errors:
            errors.extend(sub_errors)
        if is_coroutine_callable(call):
            solved = await call(**sub_values)
        else:
            solved = await run_in_threadpool(call, **sub_values)
        values[name] = solved
    return values, errors, supports


async def solve_dependencies(
    *,
    dependant: Dependant,
    ctx: Dict[str, Any] = None,
    solvers: List[Callable[[...], Any]] = None,
):
    values: Dict[str, Any] = {}
    errors: List[Any] = []
    ctx = ctx or {}
    solvers = solvers or []
    solvers.extend([solve_by_name, solve_by_call])

    sub_dependant: Dependant
    for sub_dependant in dependant.dependencies:
        for solver in solvers:
            solved_result = await solver(dependant=sub_dependant, ctx=ctx)
            (sub_values, sub_errors, supported) = solved_result
            if supported:
                values.update(sub_values)
                errors.extend(sub_errors)
                break

    return values, errors


async def call_with_deps(call: Callable[..., Any], ctx={}):
    result = await solve_dependencies(
        dependant=get_dependant(call=call, name="_"), ctx={"just_param": 10}
    )

    (values, errors) = result
    if errors:
        raise Exception(errors)
    return await call(**values)
