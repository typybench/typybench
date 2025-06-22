__all__ = [
    "compare_type_attributes",
    "get_type_similarity",
    "_get_type_info_similarity",
    "SkippedType",
    "get_mypy_type_meta",
]

import dataclasses

import mypy.nodes
import mypy.types
import numpy as np
from loguru import logger
from scipy.optimize import linear_sum_assignment


class SkippedType(RuntimeError):
    pass


@dataclasses.dataclass
class TypeMeta(object):
    depth: int
    count: int
    mypy_type: mypy.types.Type

    def __iadd__(self, other: "TypeMeta") -> "TypeMeta":
        self.depth = max(self.depth, other.depth + 1)
        self.count += other.count
        return self


def get_mypy_type_meta(t: mypy.types.Type):
    meta = TypeMeta(depth=1, count=0, mypy_type=t)
    if isinstance(t, mypy.types.UnionType):
        for x in t.items:
            meta += get_mypy_type_meta(x)
    else:
        type_name, type_origin, type_args = analyze_mypy_type(t)
        for x in type_args:
            meta += get_mypy_type_meta(x)
    meta.count += 1
    return meta


def get_type_attributes(t):
    if isinstance(t, mypy.nodes.TypeInfo):
        return t.names
    elif t == mypy.types.AnyType:
        return dir(mypy.types.Any)
    elif t == mypy.types.NoneType:
        return dir(None)
    elif t == mypy.types.TupleType:
        return dir(tuple)
    else:
        raise NotImplementedError(f"{t}: {type(t)}")


def compare_type_attributes(a_type: mypy.nodes.TypeInfo, b_type: mypy.nodes.TypeInfo):
    type1_attributes = set(get_type_attributes(a_type))
    type2_attributes = set(get_type_attributes(b_type))

    type1_minus_type2 = type1_attributes - type2_attributes
    type2_minus_type1 = type2_attributes - type1_attributes
    common = type1_attributes.intersection(type2_attributes)

    return type1_minus_type2, type2_minus_type1, common


def _get_type_info_similarity(a_type: mypy.nodes.TypeInfo, b_type: mypy.nodes.TypeInfo):
    a_b, b_a, common = compare_type_attributes(a_type, b_type)
    numerator = len(a_b) + len(b_a)
    denominator = len(common - set(dir(mypy.types.Any))) + len(a_b) + len(b_a)
    if denominator == 0 and numerator == 0:
        return 1.0
    return 1.0 - numerator / denominator


def compare_within_level(a_list, b_list, is_union: bool, debug: bool = False):
    if debug:
        logger.debug(f"Compare within level: {a_list}, {b_list}\n")

    if is_union:
        cost_matrix = np.empty([len(b_list), len(a_list)])

        for i in range(len(b_list)):
            for j in range(len(a_list)):
                if debug:
                    logger.debug(f"Compare {b_list[i]} with {a_list[j]}")
                cost_matrix[i, j] = get_type_similarity(b_list[i], a_list[j])

        if debug:
            logger.debug(
                f"Formulate a matching problem with the following cost matrix:\n{cost_matrix}"
            )

        match_1, match_2 = linear_sum_assignment(-cost_matrix)
        score = cost_matrix[match_1, match_2].sum()

        if debug:
            logger.debug("Matching result:")
            for i, j in zip(match_1, match_2):
                logger.debug(
                    f"  {b_list[i]}  <-->  {a_list[j]} "  #
                    f"Score: {cost_matrix[i, j]}"
                )
    else:
        score = 0
        for i in range(min(len(a_list), len(b_list))):
            score += get_type_similarity(a_list[i], b_list[i])

    score /= max(len(b_list), len(a_list))
    return score


def analyze_mypy_type(t: mypy.types.Type):
    if isinstance(t, mypy.types.Instance):
        return t.type.name, t.type, t.args
    elif isinstance(t, mypy.types.AnyType):
        return "Any", mypy.types.AnyType, ()
    elif isinstance(t, mypy.types.NoneType):
        return "None", mypy.types.NoneType, ()
    elif isinstance(t, mypy.types.TupleType):
        return "tuple", mypy.types.TupleType, t.items
    elif isinstance(
        t,
        (
            mypy.types.LiteralType,
            mypy.types.CallableType,
            mypy.types.TypeAliasType,
            mypy.types.TypeType,
            mypy.types.UnboundType,
            mypy.types.TypeVarType,
            mypy.types.Overloaded,
            mypy.types.UninhabitedType,
            mypy.types.UnpackType,
            mypy.types.ParamSpecType,
            mypy.types.TypedDictType,
            mypy.types.DeletedType,
            mypy.types.Parameters,
        ),
    ):
        raise SkippedType(f"{type(t)}: {t}")
    else:
        raise NotImplementedError(f"{type(t)}")


def get_type_similarity(
    a_type: mypy.types.Type, b_type: mypy.types.Type, debug: bool = False
):
    assert a_type is not None
    assert b_type is not None
    if isinstance(a_type, mypy.types.UnionType) and not isinstance(
        b_type, mypy.types.UnionType
    ):
        if debug:
            logger.debug(f"Found union, recursive call with {a_type.items}, {[b_type]}")
        return compare_within_level(a_type.items, [b_type], True)
    if not isinstance(a_type, mypy.types.UnionType) and isinstance(
        b_type, mypy.types.UnionType
    ):
        if debug:
            logger.debug(f"Found union, recursive call with {[a_type]}, {b_type.items}")
        return compare_within_level([a_type], b_type.items, True)
    if isinstance(a_type, mypy.types.UnionType) and isinstance(
        b_type, mypy.types.UnionType
    ):
        if debug:
            logger.debug(
                f"Found union, recursive call with {a_type.items}, {b_type.items}"
            )
        return compare_within_level(a_type.items, b_type.items, True)

    a_type_name, a_type_origin, a_type_args = analyze_mypy_type(a_type)
    b_type_name, b_type_origin, b_type_args = analyze_mypy_type(b_type)

    if debug:
        logger.debug(
            f"\n"  #
            f"  Type A Origin: {a_type_name}\n"
            f"  Arguments:     {a_type_args}"
        )
        logger.debug(
            f"\n"  #
            f"  Type B Origin: {b_type_name}\n"
            f"  Arguments:     {b_type_args}"
        )

    if str(a_type) == str(b_type):
        score = 1.0
    else:
        score = _get_type_info_similarity(a_type_origin, b_type_origin)
    if debug:
        logger.debug(f"Similarity between Type 1 Origin and Type 2 Origin: {score}")

    # If both types have arguments, compare them iteratively
    if a_type_args and b_type_args:
        if debug:
            logger.debug("Continue for next level")
        score = (score + compare_within_level(a_type_args, b_type_args, False)) / 2

    elif a_type_args or b_type_args:
        if debug:
            logger.debug(f"Only one has arguments, get default difference")
        score /= 2

    return score
