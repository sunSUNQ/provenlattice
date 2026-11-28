from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from provenlattice.analysis import ANALYZER_VERSIONS
from provenlattice.analysis_query import query_analysis
from provenlattice.defect_query import query_defect_candidates
from provenlattice.graph import full_index
from provenlattice.incremental import incremental_update
from provenlattice.orchestrator import analyze_scope


SOURCES = {
    "src/facts.c": r"""#define MACRO_EXTENT 32
int global_scalar;
void facts(int n) {
    char buf[64];
    int numbers[4];
    char dynamic[n];
    char macrobuf[MACRO_EXTENT];
    buf[n-1] = 0;
    char read_value = buf[5];
    *(buf+2) = 1;
    numbers[1] = 3;
    dynamic[2] = 4;
    macrobuf[0] = 0;
    char *heap_n = malloc(n);
    char *heap_16 = malloc(16);
    char *heap_calloc = calloc(4, 8);
    char *heap_calloc_n = calloc(n, sizeof(int));
    char *heap_sizeof = malloc(sizeof(heap_sizeof));
    memcpy(buf, heap_n, n);
    memset(buf, 0, 64);
}
void shadow_two(void) {
    char buf[8];
    buf[7] = 1;
}
void unknown_pointer(int *p, int n) {
    *(p+n) = 1;
}
void parameter_array(char p[64]) {
    p[1] = 0;
}
void multidimensional(void) {
    char matrix[4][8];
    matrix[1][2] = 0;
}
void scalar_write(void) {
    global_scalar = 1;
}
""",
    "src/regressions.c": r"""int global_rmw[4];
void *consume(void *);
struct AccessS { int x; };
struct MemoryS { char data[8]; };
struct OutHolder { void *slot; };
extern char *external_pointer;
void casts_and_literals(void) {
    char cast_extent[(_Bool)2];
    char octal[010];
    char access[8];
    cast_extent[0] = 0;
    octal[07] = 0;
    access[(_Bool)2] = 0;
}
void allocation_regressions(void) {
    char *aligned = memalign(16, 64);
    malloc(16);
    char *product = calloc(1+2, 3+4);
}
void allocation_product_overflow(void) {
    char *wide = calloc(65536, 65536);
    char *maximum = calloc(2147483647, 2);
    char *wide_realloc = reallocarray(0, 65536, 65536);
}
void dynamic_projection(int n) {
    int dynamic[n];
    int sum[1+2];
    signed char signed_bytes[2];
    unsigned char unsigned_bytes[3];
    unsigned/*comment*/char commented_bytes[3];
    static int (parenthesized)[4];
    const int (wrapped[5]);
    dynamic[0] = 0;
    sum[0] = 0;
    signed_bytes[0] = 0;
    unsigned_bytes[0] = 0;
    commented_bytes[0] = 0;
    parenthesized[0] = 0;
    wrapped[0] = 0;
}
void literal_length(char *p) {
    memset(p, 0, sizeof("a b"));
}
void global_rmw_access(void) {
    global_rmw[0] += 1;
}
void value_access_direction(void) {
    char a[4];
    char *p = &a[0];
    unsigned long n = sizeof(a[1]);
    *&a[2] = 3;
    *&a[3] += 1;
}
void for_scope(int n) {
    for (char scoped[4] = {0}; n; n--) { scoped[0] = 0; }
    scoped[1] = 0;
}
void statement_shadow_c(int n) {
    char for_outer[8];
    for (int for_outer = 0; n; n--) { }
    for_outer[1] = 0;
    for (int for_unresolved = 0; n; n--) { }
    for_unresolved[1] = 0;
}
void product_parentheses(int n) {
    char *conditional_product = calloc(n ? 2 : 3, 4);
    char *assignment_product = calloc(n = 2, 3);
    char *comma_product = calloc((n, 2), 3);
    int conditional[n ? 2 : 3];
    int assigned[n = 2];
    int comma[(n, 2)];
    conditional[0] = 0;
    assigned[0] = 0;
    comma[0] = 0;
}
void nested_scope(void) {
    char nested[8];
    { char nested[3]; nested[0] = 0; }
    nested[1] = 0;
}
void integer_semantics(int *v, int n) {
    char *negative = malloc(-1);
    char *negative_shift = malloc(1 << -1);
    char wrapping[4];
    wrapping[0xffffffffU + 1U] = 0;
    char *division = malloc(n / *v);
    char *unary_plus = malloc(1 + +2);
}
void negative_index_facts(int n) {
    char negative_index[4];
    negative_index[-1] = 0;
    negative_index[-(1)] = 0;
    negative_index[- 1] = 0;
    negative_index[-1 + 0] = 0;
    negative_index[-n] = 0;
    negative_index[-2147483648] = 0;
    negative_index[-2147483649] = 0;
    negative_index[-01] = 0;
    negative_index[-010] = 0;
    negative_index[- 010] = 0;
    negative_index[-(010)] = 0;
    negative_index[-0x1] = 0;
    negative_index[-(0x7fffffff)] = 0;
    negative_index[-0x80000000] = 0;
    negative_index[- 0x80000000] = 0;
    negative_index[-(0x80000000)] = 0;
    negative_index[-(020000000000)] = 0;
    negative_index[-0b10000000000000000000000000000000] = 0;
    negative_index[-1U] = 0;
    negative_index[1 << -1] = 0;
    *(negative_index + -1) = 0;
    *(negative_index + -010) = 0;
    *(negative_index + -0x80000000) = 0;
    *(negative_index - -1) = 0;
    *(negative_index - -0x80000000) = 0;
    *(negative_index - -2147483648) = 0;
}
void commuted_subscripts(int i) {
    char swapped[4];
    2[swapped] = 0;
    (-010)[swapped] = 0;
    i[swapped] = 0;
    i[(swapped)] = 0;
}
void unsupported_commuted_subscript(struct MemoryS s, int i) {
    i[s.data] = 0;
}
void commuted_identifier_targets(int i, char *p, char parameter_array[64]) {
    i[p] = 0;
    (i)[p] = 1;
    i[parameter_array] = 2;
    i[external_pointer] = 3;
    i[undeclared_target] = 4;
    p[i] = 5;
    parameter_array[i] = 6;
}
void cast_array_base(void) {
    int casted[4];
    ((unsigned char *)casted)[3] = 0;
    *((unsigned char *)casted + 3) = 0;
}
void commuted_pointer_offsets(int i, char *p) {
    char offset_array[4];
    *(i+offset_array) = 1;
    *(-010+offset_array) = 1;
    *(-0x80000000+offset_array) = 1;
    *(i+p) = 2;
    *(offset_array+i) = 3;
    *(p+i) = 4;
}
void nested_allocation_binding(void *p, void *dst) {
    p = consume(malloc(32));
    p = (malloc(64), dst);
    p = malloc(128);
}
void conditional_allocation_binding(int c, void *other) {
    void *p;
    p = c ? malloc(15360) : other;
}
void assigned_memory_call(void *r, void *dst, void *src) {
    r = memcpy(dst, src, 16);
}
void cast_memory_destinations(struct MemoryS s) {
    memset((void *)s.data, 0, 4);
    memset(&s.data, 0, 8);
}
void compound_allocation_binding(void) {
    unsigned long n = 0;
    n += (unsigned long)malloc(32);
}
void indirect_allocation_binding(void **pp) {
    *pp = malloc(32);
}
void out_argument_allocation_binding(void **pp, void *p, unsigned long handle) {
    posix_memalign(&p, 16, 32);
    posix_memalign(pp, 16, 64);
    posix_memalign((void **)*pp, 16, 128);
    posix_memalign((void **)&p, 16, 256);
    posix_memalign((void **)&handle, 16, 512);
}
void shadowed_tag_member_out_argument(void) {
    struct ShadowTag { unsigned long handle; };
    {
        struct ShadowTag { void *handle; };
    }
    struct ShadowTag s;
    posix_memalign((void **)&s.handle, 16, 1024);
}
void direct_member_value_controls(struct OutHolder s) {
    s.slot = malloc(2048);
    memset(s.slot, 0, 3072);
    posix_memalign(&s.slot, 16, 4096);
}
void member_access_direction(void) {
    struct AccessS access_members[4];
    struct AccessS *pointer_members[4];
    int *p = &access_members[1].x;
    access_members[2].x = 0;
    access_members[3].x += 1;
    pointer_members[1]->x = 0;
}
""",
    "src/regressions.cpp": r"""struct OverloadedIndex {
    int &operator[](const char *);
};
void cpp_overloaded_subscript(OverloadedIndex i) {
    char overloaded_array[4];
    i[overloaded_array] = 0;
}
struct OverloadedAddress { void **operator&(); };
struct OverloadedMemoryAddress { void *operator&(); };
struct OverloadedComma {};
void *operator,(OverloadedComma, void *);
void cpp_overloaded_address_allocation(OverloadedAddress p) {
    posix_memalign(&p, 16, 2048);
}
void cpp_overloaded_address_memory(OverloadedMemoryAddress m) {
    memset(&m, 0, 4096);
}
void cpp_overloaded_comma_allocation(OverloadedComma q, void *p) {
    p = (q, malloc(8192));
}
char overloaded_offset_target;
struct OverloadedOffset {};
char *operator+(char *, OverloadedOffset) { return &overloaded_offset_target; }
void cpp_overloaded_subscript_offset(void) {
    char offset_array[4];
    OverloadedOffset o;
    offset_array[o] = 1;
}
struct AssignmentSink { void operator=(void *); };
struct InitSink { InitSink(void *); };
void cpp_overloaded_allocation_targets(void) {
    AssignmentSink assignment_sink;
    assignment_sink = malloc(64);
    InitSink init_sink = malloc(96);
    char *pointer = (char *)malloc(128);
}
char allocation_cast_target;
struct AllocationRebind {
    AllocationRebind(void *) {}
    operator void *() { return &allocation_cast_target; }
};
void cpp_allocation_cast_conversion(void) {
    void *p;
    p = (AllocationRebind)malloc(12288);
    p = (char *)malloc(12800);
}
void cpp_conditional_allocation(bool c, void *other) {
    void *p;
    p = c ? malloc(13312) : other;
}
char overloaded_comma_target;
struct OverloadedCommaWrite {};
char &operator,(OverloadedCommaWrite, char &) { return overloaded_comma_target; }
void cpp_overloaded_comma_write(void) {
    char comma_array[4];
    OverloadedCommaWrite q;
    (q, comma_array[1]) = 2;
}
struct ReviewPair { int *a; int *b; };
namespace N {
void memset(char *, int, unsigned long) {}
}
void reviewer_scope_cast_and_memory_regressions(char *p) {
    ReviewPair pairs[1];
    char a[8];
    int numbers[4];
    for (auto [a, b] : pairs) {
        a[0] = 1;
    }
    [a = p] {
        a[0] = 1;
    }();
    ((int&)numbers[0]) = 1;
    static_cast<int&>(numbers[1]) = 2;
    N::memset(a, 0, 4);
    std::memset(a, 0, 4);
}
ReviewPair make_review_pair(int);
struct ReviewPairRange {
    ReviewPair *begin();
    ReviewPair *end();
};
void reviewer_structured_binding_scope(void) {
    ReviewPair pairs[1];
    ReviewPairRange ranges[1];
    char a[8];
    if (auto [a, b] = make_review_pair(a[1]); true) {
        a[0] = 3;
    }
    for (auto [a, b] : ranges[a[0]]) {
        a[0] = 4;
    }
}
void reviewer_lambda_capture_nested_scope(void) {
    char a[8];
    [a = &a[0]] {
        a[0] = 1;
        { int a[4]; a[0] = 2; }
    }();
}
struct OverloadedElementAddress {
    int *operator&();
    void operator=(int);
};
void cpp_overloaded_element_address(void) {
    OverloadedElementAddress address_array[4];
    address_array[1] = 3;
    *&address_array[2] = 3;
}
struct MemoryConversion { operator void *(); };
void cpp_memory_destination_conversion(MemoryConversion c, void *p) {
    memset(c, 0, 128);
    memset((void *)c, 0, 256);
    memset(p, 0, 512);
}
namespace M {
struct Same {
    OverloadedOffset i;
    AssignmentSink p;
    MemoryConversion c;
};
}
namespace N {
struct Same {
    int i;
    void *p;
    void *c;
};
}
void cpp_same_named_member_types(M::Same s) {
    char qualified_array[4];
    *(qualified_array+s.i) = 0;
    s.p = malloc(6144);
    memset(s.c, 0, 7168);
}
struct UniqueMember {
    int index;
    void *pointer;
    char data[8];
};
void cpp_unambiguous_member_types(struct UniqueMember s) {
    char member_index_array[8];
    member_index_array[s.index] = 0;
    s.pointer = malloc(9216);
    memset(s.pointer, 0, 10240);
    memset(s.data, 0, 11264);
}
struct FixedData {
    char data[8];
    void set() {
        char data[2];
        this->data[1] = 0;
        data[0] = 0;
    }
};
void cpp_cast(void) {
    char value[(bool)2];
    value[0] = 0;
}
void statement_shadow_cpp(int n, int (&values)[4]) {
    char if_array[8];
    if (char if_array[2] = ""; n) { if_array[0] = 0; }
    if_array[1] = 0;
    char switch_array[8];
    switch (char switch_array[3] = ""; n) { case 0: switch_array[0] = 0; }
    switch_array[1] = 0;
    char while_array[8];
    while (char while_array[5] = "") { while_array[0] = 0; }
    while_array[1] = 0;
    char if_scalar[8];
    if (int if_scalar = n; n) { }
    if_scalar[1] = 0;
    char switch_scalar[8];
    switch (int switch_scalar = n; n) { case 0: break; }
    switch_scalar[1] = 0;
    char while_scalar[8];
    while (int while_scalar = n) { }
    while_scalar[1] = 0;
    char range_array[8];
    for (char range_array[2] : values) { range_array[0] = 0; }
    range_array[1] = 0;
}
void legal_cpp_indices(void) {
    char legal[128];
    legal[sizeof(int)] = 0;
    legal['a'] = 0;
    legal[true] = 0;
}
void raw_string_length(char *p) {
    memset(p, 0, sizeof(R"tag(a "  b)tag"));
}
void unevaluated_and_conditional(bool c, int i) {
    int unevaluated[4];
    using T = decltype(unevaluated[0]);
    bool b = noexcept(unevaluated[1]);
    int conditional_left[4], conditional_right[4];
    (c ? conditional_left[0] : conditional_right[0]) = 1;
    char cpp_swapped[4];
    2[cpp_swapped] = 0;
    (-010)[cpp_swapped] = 0;
    i[cpp_swapped] = 0;
}
""",
    "src/memory_destinations.c": r"""struct MemoryDestinationMember { char data[4]; };
void memory_destination_golden(void) {
    char dst[4];
    memset(dst, 0, 8);
}
void memory_destination_functions(void) {
    char copy_dst[4];
    char move_dst[5];
    int numbers[4];
    char source[8];
    memcpy(copy_dst, source, 4);
    memmove(move_dst, source, 5);
    memset((void *)numbers, 0, 16);
}
void assigned_array_memory_call(void) {
    char dst[4];
    char src[4];
    char *r;
    r = memcpy(dst, src, 16);
}
void memory_destination_fail_closed(int n, char *pointer, int scalar) {
    char source[4];
    char dynamic[n];
    struct MemoryDestinationMember s;
    memcpy(pointer, source, n);
    memmove(dynamic, source, n);
    memset(s.data, 0, 4);
    memset(scalar, 0, 4);
    memset(pointer+n, 0, 4);
    memset(unresolved, 0, 4);
}
void memory_destination_statement_shadow(void) {
    char a[4];
    for (int a = 0; a < 1; ++a) { }
    memset(a, 0, 4);
}
""",
    "src/memory_destinations.cpp": r"""void std_memory_destination_extents(void) {
    char dst[4];
    char src[4];
    std::memcpy(dst, src, 4);
    std::memmove(dst, src, 4);
    std::memset(dst, 0, 8);
}
""",
    "src/facts.cpp": r"""struct Flex {
    char data[];
    void set(int i) { data[i] = 0; }
};
void cpp_facts(int n) {
    char cppbuf[8];
    cppbuf[3] = 1;
    cppbuf[-1] = 1;
    cppbuf[-010] = 1;
    cppbuf[-0x80000000] = 1;
    char *heap = malloc(n);
}
""",
}


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.encode("utf-8"))


class BufferExtentFactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        for relative, value in SOURCES.items():
            write(self.root / relative, value)
        self.database = Path(self.temp.name) / "graph.db"
        full_index(self.root, self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def materialize(self, *features: str) -> dict:
        return analyze_scope(
            self.root, "src", features or ("sparse_cfg",), database=self.database
        )

    def events(self, relative: str = "src/facts.c", feature: str = "sparse_cfg") -> list[dict]:
        result = query_analysis(
            self.root, feature, file_path=relative, database=self.database
        )
        self.assertEqual(result["status"], "available", result.get("reason"))
        return result["events"]

    def event(
        self, event_type: str, matched_name: str, relative: str = "src/facts.c"
    ) -> dict:
        matches = [
            event for event in self.events(relative)
            if event["event_type"] == event_type and event["matched_name"] == matched_name
        ]
        self.assertEqual(len(matches), 1, (event_type, matched_name, len(matches)))
        return matches[0]

    def fact(self, event: dict, key: str) -> dict:
        self.assertIn(key, event.get("annotations", {}), event)
        value = json.loads(event["annotations"][key])
        self.assertIsInstance(value, dict)
        return value

    def extent(self, event_type: str, matched_name: str, relative: str = "src/facts.c") -> dict:
        return self.fact(self.event(event_type, matched_name, relative), "buffer_extent_v1")

    def access(self, event_type: str, matched_name: str, relative: str = "src/facts.c") -> dict:
        return self.fact(self.event(event_type, matched_name, relative), "memory_access_v1")

    def test_fixed_array_has_elements_bytes_and_typed_access_facts(self) -> None:
        self.materialize()
        write_event = self.event("DEREFERENCE", "buf[n-1]")
        extent = self.fact(write_event, "buffer_extent_v1")
        self.assertEqual(extent["source"], "declared_array")
        self.assertEqual(extent["unit"], "elements")
        self.assertEqual(extent["expression"], "64")
        self.assertEqual(extent["constant"], 64)
        self.assertEqual(extent["status"], "constant")
        self.assertEqual(extent["bytes"]["constant"], 64)
        self.assertEqual(extent["bytes"]["unit"], "bytes")
        self.assertEqual(extent["object"]["decl"], "local:buf")
        self.assertTrue(write_event["event_id"].startswith("event:"))

        access = self.fact(write_event, "memory_access_v1")
        self.assertEqual(access["access"], "WRITE")
        self.assertEqual(access["kind"], "subscript")
        self.assertEqual(access["expression"], "n-1")
        self.assertIsNone(access["constant"])
        self.assertEqual(access["status"], "expression")
        self.assertEqual(access["unit"], "elements")

        read = self.access("DEREFERENCE", "buf[5]")
        self.assertEqual(read["access"], "READ")
        self.assertEqual(read["constant"], 5)
        self.assertEqual(read["status"], "constant")

        offset_event = self.event("DEREFERENCE", "*(buf+2)")
        offset = self.fact(offset_event, "memory_access_v1")
        self.assertEqual(offset["access"], "WRITE")
        self.assertEqual(offset["kind"], "pointer_offset")
        self.assertEqual(offset["constant"], 2)
        self.assertEqual(self.fact(offset_event, "buffer_extent_v1")["constant"], 64)

    def test_non_char_array_does_not_invent_target_abi_byte_size(self) -> None:
        self.materialize()
        extent = self.extent("DEREFERENCE", "numbers[1]")
        self.assertEqual(extent["unit"], "elements")
        self.assertEqual(extent["constant"], 4)
        self.assertEqual(extent["bytes"]["expression"], "4 * sizeof(int)")
        self.assertIsNone(extent["bytes"]["constant"])
        self.assertEqual(extent["bytes"]["status"], "unknown")
        self.assertIn("target ABI", extent["bytes"]["limitation"])

    def test_malloc_calloc_retain_constant_and_dynamic_sizes(self) -> None:
        self.materialize()
        # Three malloc events share a matched name; select by their size facts.
        mallocs = [
            event for event in self.events()
            if event["event_type"] == "ALLOC" and event["matched_name"] == "malloc"
        ]
        self.assertEqual(len(mallocs), 3)
        by_size = {
            self.fact(event, "buffer_extent_v1")["expression"]:
            self.fact(event, "buffer_extent_v1")
            for event in mallocs
        }
        self.assertEqual(by_size["16"]["constant"], 16)
        self.assertEqual(by_size["16"]["unit"], "bytes")
        self.assertEqual(by_size["n"]["status"], "expression")
        self.assertIsNone(by_size["n"]["constant"])
        self.assertEqual(by_size["sizeof(heap_sizeof)"]["status"], "expression")
        self.assertIsNone(by_size["sizeof(heap_sizeof)"]["constant"])

        callocs = [
            self.fact(event, "buffer_extent_v1")
            for event in self.events()
            if event["event_type"] == "ALLOC" and event["matched_name"] == "calloc"
        ]
        self.assertEqual(len(callocs), 2)
        fixed = next(fact for fact in callocs if fact["status"] == "constant")
        dynamic = next(fact for fact in callocs if fact["status"] == "expression")
        self.assertEqual(fixed["constant"], 32)
        self.assertEqual(fixed["count_expression"], "4")
        self.assertEqual(fixed["element_size_expression"], "8")
        self.assertEqual(dynamic["count_expression"], "n")
        self.assertEqual(dynamic["element_size_expression"], "sizeof(int)")
        self.assertIsNone(dynamic["constant"])

    def test_memory_api_length_is_a_call_fact_in_bytes(self) -> None:
        self.materialize()
        lengths = [
            self.fact(event, "memory_access_v1")
            for event in self.events()
            if "memory_access_v1" in event.get("annotations", {})
            and self.fact(event, "memory_access_v1")["kind"] == "memory_length"
        ]
        self.assertEqual(len(lengths), 2)
        by_function = {fact["function"]: fact for fact in lengths}
        self.assertEqual(by_function["memcpy"]["access"], "CALL")
        self.assertEqual(by_function["memcpy"]["expression"], "n")
        self.assertIsNone(by_function["memcpy"]["constant"])
        self.assertEqual(by_function["memcpy"]["unit"], "bytes")
        self.assertEqual(by_function["memset"]["constant"], 64)
        self.assertEqual(by_function["memset"]["status"], "constant")

    def test_memory_call_destination_extent_golden(self) -> None:
        self.materialize()
        relative = "src/memory_destinations.c"
        events = [
            event for event in self.events(relative)
            if event["owner_qualified_name"] == "memory_destination_golden"
        ]
        call = next(event for event in events if event["event_type"] == "CALL")
        self.assertFalse(any(event["event_type"] == "DEREFERENCE" for event in events))

        access = self.fact(call, "memory_access_v1")
        self.assertEqual(access["kind"], "memory_length")
        self.assertEqual(access["function"], "memset")
        self.assertEqual(access["unit"], "bytes")
        self.assertEqual(access["constant"], 8)
        self.assertEqual(access["object"]["decl"], "local:dst")

        extent = self.fact(call, "buffer_extent_v1")
        self.assertEqual(extent["source"], "declared_array")
        self.assertEqual(extent["unit"], "elements")
        self.assertEqual(extent["constant"], 4)
        self.assertEqual(extent["status"], "constant")
        self.assertEqual(extent["bytes"]["unit"], "bytes")
        self.assertEqual(extent["bytes"]["constant"], 4)
        self.assertEqual(extent["bytes"]["status"], "constant")
        self.assertEqual(extent["object"]["decl"], "local:dst")
        self.assertIn("scoped_decl", extent["object"])
        self.assertEqual(
            {key: value for key, value in extent["object"].items() if key != "scoped_decl"},
            access["object"],
        )

    def test_memory_api_destination_extents_cover_functions_units_and_assignment(self) -> None:
        self.materialize()
        relative = "src/memory_destinations.c"
        lines = SOURCES[relative].splitlines()
        calls = {
            (event["owner_qualified_name"], lines[event["start_line"] - 1].strip()): event
            for event in self.events(relative)
            if event["event_type"] == "CALL"
        }
        expected = {
            "memcpy(copy_dst, source, 4);": ("local:copy_dst", 4),
            "memmove(move_dst, source, 5);": ("local:move_dst", 5),
        }
        for line, (declaration, size) in expected.items():
            event = calls[("memory_destination_functions", line)]
            extent = self.fact(event, "buffer_extent_v1")
            self.assertEqual(extent["object"]["decl"], declaration)
            self.assertEqual(extent["constant"], size)
            self.assertEqual(extent["bytes"]["constant"], size)
            self.assertEqual(
                self.fact(event, "memory_access_v1")["object"]["decl"], declaration
            )

        numbers = calls[("memory_destination_functions", "memset((void *)numbers, 0, 16);")]
        extent = self.fact(numbers, "buffer_extent_v1")
        self.assertEqual(extent["object"]["decl"], "local:numbers")
        self.assertEqual(extent["constant"], 4)
        self.assertEqual(extent["unit"], "elements")
        self.assertEqual(extent["bytes"]["expression"], "4 * sizeof(int)")
        self.assertIsNone(extent["bytes"]["constant"])
        self.assertEqual(extent["bytes"]["status"], "unknown")
        self.assertIn("target ABI", extent["bytes"]["limitation"])

        assigned = calls[("assigned_array_memory_call", "r = memcpy(dst, src, 16);")]
        access = self.fact(assigned, "memory_access_v1")
        extent = self.fact(assigned, "buffer_extent_v1")
        self.assertEqual(access["object"]["decl"], "local:dst")
        self.assertEqual(extent["object"]["decl"], "local:dst")
        self.assertNotEqual(extent["object"]["decl"], "local:r")
        self.assertEqual(extent["constant"], 4)
        self.assertEqual(access["constant"], 16)

    def test_memory_call_destination_extent_fail_closed_boundaries(self) -> None:
        self.materialize()
        relative = "src/memory_destinations.c"
        lines = SOURCES[relative].splitlines()
        calls = {
            lines[event["start_line"] - 1].strip(): event
            for event in self.events(relative)
            if event["owner_qualified_name"] == "memory_destination_fail_closed"
            and event["event_type"] == "CALL"
        }

        pointer = self.fact(calls["memcpy(pointer, source, n);"], "buffer_extent_v1")
        self.assertEqual(pointer["source"], "unknown")
        self.assertEqual(pointer["status"], "unknown")
        self.assertIsNone(pointer["constant"])
        self.assertEqual(pointer["object"]["decl"], "parameter:pointer")

        dynamic = self.fact(calls["memmove(dynamic, source, n);"], "buffer_extent_v1")
        self.assertEqual(dynamic["status"], "unknown")
        self.assertEqual(dynamic["expression"], "n")
        self.assertIsNone(dynamic["constant"])
        self.assertEqual(dynamic["object"]["decl"], "local:dynamic")

        member_event = calls["memset(s.data, 0, 4);"]
        member = self.fact(member_event, "buffer_extent_v1")
        member_access = self.fact(member_event, "memory_access_v1")
        self.assertEqual(member["source"], "unknown")
        self.assertEqual(member["status"], "unknown")
        self.assertEqual(member["object"]["decl"], "local:s")
        self.assertEqual(member["object"]["member"], "data")
        self.assertEqual(member_access["object"], member["object"])

        unresolved = self.fact(calls["memset(unresolved, 0, 4);"], "buffer_extent_v1")
        self.assertEqual(unresolved["source"], "unknown")
        self.assertEqual(unresolved["status"], "unknown")
        self.assertEqual(unresolved["object"]["decl"], "")
        for line in ("memset(scalar, 0, 4);", "memset(pointer+n, 0, 4);"):
            self.assertNotIn(
                "buffer_extent_v1", calls[line].get("annotations", {}), line
            )

    def test_memory_call_destination_identity_uses_extent_scope_overlay(self) -> None:
        self.materialize()
        event = next(
            event for event in self.events("src/memory_destinations.c")
            if event["owner_qualified_name"] == "memory_destination_statement_shadow"
            and event["event_type"] == "CALL"
        )
        access = self.fact(event, "memory_access_v1")
        extent = self.fact(event, "buffer_extent_v1")
        self.assertEqual(access["object"]["decl"], "local:a")
        self.assertEqual(access["object"]["type"], "char")
        self.assertEqual(extent["object"]["type"], "char")
        self.assertEqual(extent["constant"], 4)
        self.assertEqual(
            {key: value for key, value in extent["object"].items() if key != "scoped_decl"},
            access["object"],
        )

    def test_exact_std_memory_apis_share_destination_extent_contract(self) -> None:
        self.materialize()
        relative = "src/memory_destinations.cpp"
        lines = SOURCES[relative].splitlines()
        calls = {
            lines[event["start_line"] - 1].strip(): event
            for event in self.events(relative)
            if event["event_type"] == "CALL"
        }
        for function, line in (
            ("std::memcpy", "std::memcpy(dst, src, 4);"),
            ("std::memmove", "std::memmove(dst, src, 4);"),
            ("std::memset", "std::memset(dst, 0, 8);"),
        ):
            event = calls[line]
            access = self.fact(event, "memory_access_v1")
            extent = self.fact(event, "buffer_extent_v1")
            self.assertEqual(access["function"], function)
            self.assertEqual(access["object"]["decl"], "local:dst")
            self.assertEqual(extent["object"]["decl"], "local:dst")
            self.assertEqual(extent["constant"], 4)
            self.assertEqual(extent["bytes"]["constant"], 4)

    def test_unknown_vla_macro_pointer_and_parameter_extents_stay_unknown(self) -> None:
        self.materialize()
        for name in ("dynamic[2]", "macrobuf[0]"):
            extent = self.extent("DEREFERENCE", name)
            self.assertEqual(extent["status"], "unknown", name)
            self.assertIsNone(extent["constant"], name)
            self.assertTrue(extent["expression"], name)
            self.assertTrue(extent["limitation"], name)

        pointer_event = self.event("DEREFERENCE", "*(p+n)")
        pointer_extent = self.fact(pointer_event, "buffer_extent_v1")
        self.assertEqual(pointer_extent["source"], "unknown")
        self.assertEqual(pointer_extent["status"], "unknown")
        self.assertIsNone(pointer_extent["constant"])
        pointer_access = self.fact(pointer_event, "memory_access_v1")
        self.assertEqual(pointer_access["expression"], "n")
        self.assertIsNone(pointer_access["constant"])

        parameter = self.extent("DEREFERENCE", "p[1]")
        self.assertEqual(parameter["source"], "unknown")
        self.assertIsNone(parameter["constant"])
        self.assertNotEqual(parameter["status"], "constant")

    def test_flexible_and_multidimensional_arrays_are_not_proven_extents(self) -> None:
        self.materialize()
        flexible = self.extent("DEREFERENCE", "data[i]", "src/facts.cpp")
        self.assertEqual(flexible["status"], "unsupported")
        self.assertIsNone(flexible["constant"])
        self.assertIn("flexible", flexible["limitation"])

        matrix = self.extent("DEREFERENCE", "matrix[1][2]")
        self.assertEqual(matrix["status"], "unknown")
        self.assertIsNone(matrix["constant"])

    def test_cpp_subscript_uses_the_same_versioned_contract(self) -> None:
        self.materialize()
        event = self.event("DEREFERENCE", "cppbuf[3]", "src/facts.cpp")
        extent = self.fact(event, "buffer_extent_v1")
        access = self.fact(event, "memory_access_v1")
        self.assertEqual(extent["constant"], 8)
        self.assertEqual(extent["bytes"]["constant"], 8)
        self.assertEqual(access["access"], "WRITE")
        self.assertEqual(access["expression"], "3")
        self.assertEqual(access["constant"], 3)
        negative = self.access("DEREFERENCE", "cppbuf[-1]", "src/facts.cpp")
        self.assertEqual(negative["status"], "constant")
        self.assertEqual(negative["constant"], -1)
        octal = self.access("DEREFERENCE", "cppbuf[-010]", "src/facts.cpp")
        self.assertEqual(octal["status"], "constant")
        self.assertEqual(octal["constant"], -8)
        non_decimal_minimum = self.access(
            "DEREFERENCE", "cppbuf[-0x80000000]", "src/facts.cpp"
        )
        self.assertEqual(non_decimal_minimum["status"], "expression")
        self.assertIsNone(non_decimal_minimum["constant"])

    def test_same_named_arrays_keep_declaration_and_owner_identity(self) -> None:
        self.materialize()
        first = self.event("DEREFERENCE", "buf[n-1]")
        second = self.event("DEREFERENCE", "buf[7]")
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertNotEqual(first["owner_symbol_id"], second["owner_symbol_id"])
        self.assertEqual(self.fact(first, "buffer_extent_v1")["constant"], 64)
        self.assertEqual(self.fact(second, "buffer_extent_v1")["constant"], 8)

    def test_non_array_scalar_has_no_buffer_or_index_fact(self) -> None:
        self.materialize()
        event = self.event("WRITE", "global_scalar")
        self.assertNotIn("buffer_extent_v1", event.get("annotations", {}))
        self.assertNotIn("memory_access_v1", event.get("annotations", {}))

    def test_cast_does_not_fold_and_c_octal_is_supported(self) -> None:
        self.materialize()
        relative = "src/regressions.c"
        cast_extent = self.extent("DEREFERENCE", "cast_extent[0]", relative)
        self.assertEqual(cast_extent["status"], "unknown")
        self.assertIsNone(cast_extent["constant"])
        cast_index = self.access("DEREFERENCE", "access[(_Bool)2]", relative)
        self.assertEqual(cast_index["status"], "expression")
        self.assertEqual(cast_index["expression"], "(_Bool)2")
        self.assertIsNone(cast_index["constant"])

        octal = self.extent("DEREFERENCE", "octal[07]", relative)
        self.assertEqual(octal["constant"], 8)
        self.assertEqual(octal["bytes"]["constant"], 8)
        self.assertEqual(self.access("DEREFERENCE", "octal[07]", relative)["constant"], 7)
        cpp_cast = self.extent("DEREFERENCE", "value[0]", "src/regressions.cpp")
        self.assertNotEqual(cpp_cast["status"], "constant")
        self.assertIsNone(cpp_cast["constant"])

    def test_memalign_unbound_allocation_and_compound_calloc(self) -> None:
        self.materialize()
        relative = "src/regressions.c"
        aligned = self.extent("ALLOC", "memalign", relative)
        self.assertEqual(aligned["expression"], "64")
        self.assertEqual(aligned["constant"], 64)
        self.assertEqual(aligned["object"]["decl"], "local:aligned")

        unbound = next(
            self.fact(event, "buffer_extent_v1")
            for event in self.events(relative)
            if event["event_type"] == "ALLOC" and event["matched_name"] == "malloc"
            if self.fact(event, "buffer_extent_v1")["constant"] == 16
        )
        self.assertEqual(unbound["constant"], 16)
        self.assertEqual(unbound["object"]["decl"], "")
        self.assertEqual(unbound["object"]["storage"], "unknown")
        products = [
            self.fact(event, "buffer_extent_v1")
            for event in self.events(relative)
            if event["event_type"] == "ALLOC" and event["matched_name"] == "calloc"
        ]
        product = next(fact for fact in products if fact["constant"] == 21)
        self.assertEqual(product["expression"], "(1+2) * (3+4)")

    def test_character_and_dynamic_byte_projections_keep_their_units(self) -> None:
        self.materialize()
        relative = "src/regressions.c"
        signed = self.extent("DEREFERENCE", "signed_bytes[0]", relative)
        unsigned = self.extent("DEREFERENCE", "unsigned_bytes[0]", relative)
        self.assertEqual(signed["bytes"]["constant"], 2)
        self.assertEqual(unsigned["bytes"]["constant"], 3)

        dynamic = self.extent("DEREFERENCE", "dynamic[0]", relative)
        self.assertEqual(dynamic["unit"], "elements")
        self.assertEqual(dynamic["bytes"]["unit"], "bytes")
        self.assertEqual(dynamic["bytes"]["expression"], "n * sizeof(int)")
        self.assertIsNone(dynamic["bytes"]["constant"])
        compound = self.extent("DEREFERENCE", "sum[0]", relative)
        self.assertEqual(compound["constant"], 3)
        self.assertEqual(compound["bytes"]["expression"], "(1+2) * sizeof(int)")

        commented = self.extent("DEREFERENCE", "commented_bytes[0]", relative)
        self.assertEqual(commented["constant"], 3)
        self.assertEqual(commented["bytes"]["constant"], 3)
        parenthesized = self.extent("DEREFERENCE", "parenthesized[0]", relative)
        wrapped = self.extent("DEREFERENCE", "wrapped[0]", relative)
        self.assertEqual(parenthesized["constant"], 4)
        self.assertEqual(parenthesized["bytes"]["expression"], "4 * sizeof(int)")
        self.assertEqual(wrapped["constant"], 5)

    def test_product_composition_parenthesizes_lower_precedence_operands(self) -> None:
        self.materialize()
        relative = "src/regressions.c"
        products = {
            fact["count_expression"]: fact
            for event in self.events(relative)
            if event["event_type"] == "ALLOC" and event["matched_name"] == "calloc"
            for fact in [self.fact(event, "buffer_extent_v1")]
            if "count_expression" in fact
        }
        self.assertEqual(products["n?2:3"]["expression"], "(n?2:3) * 4")
        self.assertEqual(products["n=2"]["expression"], "(n=2) * 3")
        self.assertEqual(products["(n,2)"]["expression"], "(n,2) * 3")

        for name, expression in (
            ("conditional[0]", "(n?2:3) * sizeof(int)"),
            ("assigned[0]", "(n=2) * sizeof(int)"),
            ("comma[0]", "(n,2) * sizeof(int)"),
        ):
            extent = self.extent("DEREFERENCE", name, relative)
            self.assertEqual(extent["bytes"]["expression"], expression)
            self.assertIsNone(extent["bytes"]["constant"])

    def test_fact_expression_preserves_string_literal_whitespace(self) -> None:
        self.materialize()
        lengths = [
            self.fact(event, "memory_access_v1")
            for event in self.events("src/regressions.c")
            if event["owner_qualified_name"] == "literal_length"
            and "memory_access_v1" in event.get("annotations", {})
            and self.fact(event, "memory_access_v1")["kind"] == "memory_length"
        ]
        self.assertEqual(len(lengths), 1)
        length = lengths[0]
        self.assertEqual(length["function"], "memset")
        self.assertEqual(length["expression"], 'sizeof("a b")')
        self.assertEqual(length["status"], "expression")
        self.assertIsNone(length["constant"])

        raw = next(
            self.fact(event, "memory_access_v1")
            for event in self.events("src/regressions.cpp")
            if event["event_type"] == "CALL"
            and event["owner_qualified_name"] == "raw_string_length"
            and "memory_access_v1" in event.get("annotations", {})
        )
        self.assertEqual(raw["expression"], 'sizeof(R"tag(a "  b)tag")')
        self.assertEqual(raw["status"], "expression")
        self.assertIsNone(raw["constant"])

    def test_legal_cpp_index_expressions_are_not_marked_unparsed(self) -> None:
        self.materialize()
        relative = "src/regressions.cpp"
        for matched_name, expression in (
            ("legal[sizeof(int)]", "sizeof(int)"),
            ("legal['a']", "'a'"),
            ("legal[true]", "true"),
        ):
            access = self.access("DEREFERENCE", matched_name, relative)
            self.assertEqual(access["expression"], expression)
            self.assertEqual(access["status"], "expression")
            self.assertIsNone(access["constant"])
            self.assertNotIn("unparsed", access["limitation"])

    def test_access_direction_excludes_non_value_uses_and_keeps_rmw(self) -> None:
        self.materialize()
        relative = "src/regressions.c"
        write = self.event("WRITE", "global_rmw[0]", relative)
        self.assertEqual(self.fact(write, "memory_access_v1")["access"], "READ_MODIFY_WRITE")
        read = self.event("READ", "global_rmw[0]", relative)
        self.assertEqual(self.fact(read, "memory_access_v1")["access"], "READ")
        self.assertEqual(
            self.access("DEREFERENCE", "global_rmw[0]", relative)["access"],
            "READ_MODIFY_WRITE",
        )

        address = self.event("DEREFERENCE", "a[0]", relative)
        self.assertNotIn("memory_access_v1", address.get("annotations", {}))
        sizeof_operand = [
            event for event in self.events(relative)
            if event["event_type"] == "DEREFERENCE"
            and event["matched_name"] == "a[1]"
        ]
        # `sizeof(a[1])` is not an address computation: it never evaluates the
        # subscript, so it has neither a value-access fact nor a structural
        # DEREFERENCE point (and therefore no extent fact either).
        self.assertEqual(sizeof_operand, [])
        self.assertEqual(self.access("DEREFERENCE", "a[2]", relative)["access"], "WRITE")
        self.assertEqual(
            self.access("DEREFERENCE", "a[3]", relative)["access"],
            "READ_MODIFY_WRITE",
        )

    def test_statement_and_nested_scopes_do_not_leak_array_identity(self) -> None:
        self.materialize()
        relative = "src/regressions.c"
        inside = self.extent("DEREFERENCE", "scoped[0]", relative)
        outside = self.extent("DEREFERENCE", "scoped[1]", relative)
        self.assertEqual(inside["constant"], 4)
        self.assertEqual(outside["source"], "unknown")
        self.assertIsNone(outside["constant"])
        self.assertEqual(outside["object"]["decl"], "")

        inner = self.extent("DEREFERENCE", "nested[0]", relative)
        outer = self.extent("DEREFERENCE", "nested[1]", relative)
        self.assertEqual((inner["constant"], outer["constant"]), (3, 8))
        self.assertNotEqual(inner["object"]["scoped_decl"], outer["object"]["scoped_decl"])

    def test_statement_local_shadows_resume_outer_or_empty_identity(self) -> None:
        self.materialize()
        c_outer = self.extent("DEREFERENCE", "for_outer[1]", "src/regressions.c")
        self.assertEqual(c_outer["constant"], 8)
        self.assertEqual(c_outer["object"]["storage"], "local")
        c_unknown = self.extent("DEREFERENCE", "for_unresolved[1]", "src/regressions.c")
        self.assertEqual(c_unknown["source"], "unknown")
        self.assertIsNone(c_unknown["constant"])
        self.assertEqual(c_unknown["object"]["decl"], "")
        self.assertEqual(c_unknown["object"]["storage"], "unknown")

        relative = "src/regressions.cpp"
        for stem, inner_extent in (("if_array", 2), ("switch_array", 3), ("while_array", 5)):
            inner = self.extent("DEREFERENCE", f"{stem}[0]", relative)
            outer = self.extent("DEREFERENCE", f"{stem}[1]", relative)
            self.assertEqual(inner["constant"], inner_extent, stem)
            self.assertEqual(outer["constant"], 8, stem)
            self.assertNotEqual(inner["object"]["scoped_decl"], outer["object"]["scoped_decl"])
        for stem in ("if_scalar", "switch_scalar", "while_scalar"):
            outer = self.extent("DEREFERENCE", f"{stem}[1]", relative)
            self.assertEqual(outer["constant"], 8, stem)
            self.assertEqual(outer["object"]["storage"], "local", stem)

        range_inner = self.extent("DEREFERENCE", "range_array[0]", relative)
        range_outer = self.extent("DEREFERENCE", "range_array[1]", relative)
        self.assertEqual(range_inner["source"], "unknown")
        self.assertIsNone(range_inner["constant"])
        self.assertEqual(range_inner["object"]["decl"], "")
        self.assertEqual(range_outer["constant"], 8)

    def test_explicit_this_member_cannot_borrow_same_named_local(self) -> None:
        self.materialize()
        relative = "src/regressions.cpp"
        member = self.extent("DEREFERENCE", "this->data[1]", relative)
        local = self.extent("DEREFERENCE", "data[0]", relative)
        self.assertEqual(member["constant"], 8)
        self.assertEqual(member["object"]["storage"], "field")
        self.assertEqual(local["constant"], 2)
        self.assertEqual(local["object"]["storage"], "local")

    def test_integer_folding_fails_closed_and_preserves_operator_tokens(self) -> None:
        self.materialize()
        relative = "src/regressions.c"
        allocations = {
            fact["expression"]: fact
            for event in self.events(relative)
            if event["event_type"] == "ALLOC" and event["matched_name"] == "malloc"
            for fact in [self.fact(event, "buffer_extent_v1")]
        }
        for expression in ("-1", "1<<-1"):
            self.assertIsNone(allocations[expression]["constant"])
            self.assertNotEqual(allocations[expression]["status"], "constant")
        self.assertEqual(allocations["n/ *v"]["expression"], "n/ *v")
        self.assertIsNone(allocations["n/ *v"]["constant"])
        self.assertEqual(allocations["1+ +2"]["constant"], 3)

        wrapped = self.access(
            "DEREFERENCE", "wrapping[0xffffffffU+1U]", relative
        )
        self.assertEqual(wrapped["expression"], "0xffffffffU+1U")
        self.assertIsNone(wrapped["constant"])
        self.assertNotEqual(wrapped["status"], "constant")

    def test_negative_index_and_pointer_offset_constants_are_signed_int(self) -> None:
        self.materialize()
        relative = "src/regressions.c"
        lines = SOURCES[relative].splitlines()
        events = {
            lines[event["start_line"] - 1].strip(): event
            for event in self.events(relative)
            if event["owner_qualified_name"] == "negative_index_facts"
            and event["event_type"] == "DEREFERENCE"
        }
        for line, expected in (
            ("negative_index[-1] = 0;", -1),
            ("negative_index[-(1)] = 0;", -1),
            ("negative_index[- 1] = 0;", -1),
            ("negative_index[-1 + 0] = 0;", -1),
            ("negative_index[-01] = 0;", -1),
            ("negative_index[-010] = 0;", -8),
            ("negative_index[- 010] = 0;", -8),
            ("negative_index[-(010)] = 0;", -8),
            ("negative_index[-0x1] = 0;", -1),
            ("negative_index[-(0x7fffffff)] = 0;", -2_147_483_647),
        ):
            access = self.fact(events[line], "memory_access_v1")
            self.assertEqual(access["status"], "constant", line)
            self.assertEqual(access["constant"], expected, line)
        minimum = self.fact(
            events["negative_index[-2147483648] = 0;"], "memory_access_v1"
        )
        self.assertEqual(minimum["status"], "constant")
        self.assertEqual(minimum["constant"], -2_147_483_648)

        for line in (
            "negative_index[-n] = 0;",
            "negative_index[-2147483649] = 0;",
            "negative_index[-0x80000000] = 0;",
            "negative_index[- 0x80000000] = 0;",
            "negative_index[-(0x80000000)] = 0;",
            "negative_index[-(020000000000)] = 0;",
            "negative_index[-0b10000000000000000000000000000000] = 0;",
            "negative_index[-1U] = 0;",
            "negative_index[1 << -1] = 0;",
            "*(negative_index + -0x80000000) = 0;",
            "*(negative_index - -0x80000000) = 0;",
            "*(negative_index - -2147483648) = 0;",
        ):
            access = self.fact(events[line], "memory_access_v1")
            self.assertEqual(access["status"], "expression", line)
            self.assertIsNone(access["constant"], line)

        plus = self.fact(events["*(negative_index + -1) = 0;"], "memory_access_v1")
        self.assertEqual((plus["kind"], plus["constant"]), ("pointer_offset", -1))
        octal = self.fact(events["*(negative_index + -010) = 0;"], "memory_access_v1")
        self.assertEqual((octal["kind"], octal["constant"]), ("pointer_offset", -8))
        minus = self.fact(events["*(negative_index - -1) = 0;"], "memory_access_v1")
        self.assertEqual((minus["kind"], minus["constant"]), ("pointer_offset", 1))

    def test_calloc_like_product_overflow_fails_closed(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.c")
            if event["event_type"] == "ALLOC"
            and event["owner_qualified_name"] == "allocation_product_overflow"
        ]
        self.assertEqual(len(events), 3)
        facts = [self.fact(event, "buffer_extent_v1") for event in events]
        self.assertEqual(
            {fact["expression"] for fact in facts},
            {"65536 * 65536", "2147483647 * 2"},
        )
        for fact in facts:
            self.assertIsNone(fact["constant"])
            self.assertNotEqual(fact["status"], "constant")
            self.assertTrue(fact["limitation"])

    def test_commuted_subscripts_keep_index_and_array_object(self) -> None:
        self.materialize()
        for relative, array in (("src/regressions.c", "swapped"), ("src/regressions.cpp", "cpp_swapped")):
            constant_event = self.event("DEREFERENCE", f"2[{array}]", relative)
            constant = self.fact(constant_event, "memory_access_v1")
            extent = self.fact(constant_event, "buffer_extent_v1")
            self.assertEqual(constant["constant"], 2)
            self.assertEqual(constant["expression"], "2")
            self.assertEqual(extent["constant"], 4)
            self.assertEqual(extent["object"]["decl"], f"local:{array}")

            negative_event = self.event("DEREFERENCE", f"(-010)[{array}]", relative)
            negative = self.fact(negative_event, "memory_access_v1")
            self.assertEqual(negative["status"], "constant")
            self.assertEqual(negative["constant"], -8)
            self.assertEqual(negative["expression"], "(-010)")

            dynamic_event = self.event("DEREFERENCE", f"i[{array}]", relative)
            dynamic = self.fact(dynamic_event, "memory_access_v1")
            dynamic_extent = self.fact(dynamic_event, "buffer_extent_v1")
            self.assertEqual(dynamic["expression"], "i")
            self.assertIsNone(dynamic["constant"])
            self.assertEqual(dynamic_extent["constant"], 4)
            self.assertEqual(dynamic_extent["object"]["decl"], f"local:{array}")

    def test_parenthesized_commuted_subscript_keeps_array_and_index(self) -> None:
        self.materialize()
        event = self.event("DEREFERENCE", "i[(swapped)]", "src/regressions.c")
        access = self.fact(event, "memory_access_v1")
        extent = self.fact(event, "buffer_extent_v1")
        self.assertEqual(access["expression"], "i")
        self.assertIsNone(access["constant"])
        self.assertEqual(access["object"]["decl"], "local:swapped")
        self.assertEqual(extent["constant"], 4)
        self.assertEqual(extent["object"]["decl"], "local:swapped")

    def test_cpp_overloaded_subscript_does_not_borrow_array_extent(self) -> None:
        self.materialize()
        event = self.event(
            "DEREFERENCE", "i[overloaded_array]", "src/regressions.cpp"
        )
        access = self.fact(event, "memory_access_v1")
        extent = self.fact(event, "buffer_extent_v1")
        self.assertEqual(access["status"], "unknown")
        self.assertIsNone(access["expression"])
        self.assertEqual(access["object"]["decl"], "")
        self.assertEqual(extent["source"], "unknown")
        self.assertIsNone(extent["constant"])
        self.assertEqual(extent["object"]["decl"], "")

    def test_cpp_overloaded_address_of_does_not_bind_source_object(self) -> None:
        self.materialize()
        allocation = self.extent("ALLOC", "posix_memalign", "src/regressions.cpp")
        self.assertEqual(allocation["constant"], 2048)
        self.assertEqual(allocation["object"]["decl"], "")
        self.assertEqual(allocation["object"]["storage"], "unknown")
        events = [
            event for event in self.events("src/regressions.cpp")
            if event["event_type"] == "CALL"
            and event["owner_qualified_name"] == "cpp_overloaded_address_memory"
        ]
        self.assertEqual(len(events), 1)
        access = self.fact(events[0], "memory_access_v1")
        self.assertEqual(access["constant"], 4096)
        self.assertEqual(access["object"]["decl"], "")
        self.assertEqual(access["object"]["storage"], "unknown")

    def test_cpp_overloaded_comma_does_not_bind_allocation_result(self) -> None:
        self.materialize()
        event = next(
            event for event in self.events("src/regressions.cpp")
            if event["event_type"] == "ALLOC"
            and event["owner_qualified_name"] == "cpp_overloaded_comma_allocation"
        )
        extent = self.fact(event, "buffer_extent_v1")
        self.assertEqual(extent["constant"], 8192)
        self.assertEqual(extent["object"]["decl"], "")
        self.assertEqual(extent["object"]["storage"], "unknown")

    def test_cpp_overloaded_subscript_offset_does_not_borrow_array_extent(self) -> None:
        self.materialize()
        event = self.event(
            "DEREFERENCE", "offset_array[o]", "src/regressions.cpp"
        )
        access = self.fact(event, "memory_access_v1")
        extent = self.fact(event, "buffer_extent_v1")
        self.assertEqual(access["status"], "unknown")
        self.assertIsNone(access["expression"])
        self.assertEqual(access["object"]["decl"], "")
        self.assertEqual(extent["source"], "unknown")
        self.assertIsNone(extent["constant"])
        self.assertEqual(extent["object"]["decl"], "")

    def test_cpp_overloaded_assignment_and_initialization_do_not_bind_allocation(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.cpp")
            if event["event_type"] == "ALLOC"
            and event["owner_qualified_name"] == "cpp_overloaded_allocation_targets"
        ]
        self.assertEqual(len(events), 3)
        allocations = {
            self.fact(event, "buffer_extent_v1")["constant"]:
            self.fact(event, "buffer_extent_v1")
            for event in events
        }
        self.assertEqual(set(allocations), {64, 96, 128})
        for size in (64, 96):
            self.assertEqual(allocations[size]["object"]["decl"], "")
            self.assertEqual(allocations[size]["object"]["storage"], "unknown")
        self.assertEqual(allocations[128]["object"]["decl"], "local:pointer")

    def test_cpp_class_cast_and_conditional_do_not_bind_allocation(self) -> None:
        self.materialize()
        relative = "src/regressions.cpp"
        cast_events = [
            event for event in self.events(relative)
            if event["event_type"] == "ALLOC"
            and event["owner_qualified_name"] == "cpp_allocation_cast_conversion"
        ]
        self.assertEqual(len(cast_events), 2)
        allocations = {
            self.fact(event, "buffer_extent_v1")["constant"]:
            self.fact(event, "buffer_extent_v1")
            for event in cast_events
        }
        self.assertEqual(set(allocations), {12288, 12800})
        self.assertEqual(allocations[12288]["object"]["decl"], "")
        self.assertEqual(allocations[12288]["object"]["storage"], "unknown")
        self.assertEqual(allocations[12800]["object"]["decl"], "local:p")

        conditional = next(
            event for event in self.events(relative)
            if event["event_type"] == "ALLOC"
            and event["owner_qualified_name"] == "cpp_conditional_allocation"
        )
        extent = self.fact(conditional, "buffer_extent_v1")
        self.assertEqual(extent["constant"], 13312)
        self.assertEqual(extent["object"]["decl"], "")
        self.assertEqual(extent["object"]["storage"], "unknown")

    def test_c_conditional_allocation_result_remains_bound(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.c")
            if event["event_type"] == "ALLOC"
            and event["owner_qualified_name"] == "conditional_allocation_binding"
        ]
        self.assertEqual(len(events), 1)
        extent = self.fact(events[0], "buffer_extent_v1")
        self.assertEqual(extent["constant"], 15360)
        self.assertEqual(extent["object"]["decl"], "local:p")

    def test_cpp_overloaded_comma_does_not_propagate_outer_write(self) -> None:
        self.materialize()
        event = self.event("DEREFERENCE", "comma_array[1]", "src/regressions.cpp")
        self.assertNotIn("memory_access_v1", event.get("annotations", {}))
        self.assertEqual(self.fact(event, "buffer_extent_v1")["constant"], 4)

    def test_cpp_class_element_operators_do_not_create_builtin_access(self) -> None:
        self.materialize()
        for matched_name in ("address_array[1]", "address_array[2]"):
            event = self.event("DEREFERENCE", matched_name, "src/regressions.cpp")
            self.assertNotIn("memory_access_v1", event.get("annotations", {}))
            self.assertEqual(self.fact(event, "buffer_extent_v1")["constant"], 4)

    def test_cpp_structured_binding_and_init_capture_hide_outer_array(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.cpp")
            if event["owner_qualified_name"]
            == "reviewer_scope_cast_and_memory_regressions"
            and event["matched_name"] == "a[0]"
        ]
        self.assertEqual(len(events), 2)
        for event in events:
            extent = self.fact(event, "buffer_extent_v1")
            self.assertEqual(extent["source"], "unknown")
            self.assertIsNone(extent["constant"])
            self.assertEqual(extent["object"]["decl"], "")
            self.assertEqual(extent["object"]["storage"], "unknown")

    def test_cpp_structured_binding_visibility_excludes_initializers(self) -> None:
        self.materialize()
        relative = "src/regressions.cpp"
        lines = SOURCES[relative].splitlines()
        events = {
            lines[event["start_line"] - 1].strip(): event
            for event in self.events(relative)
            if event["owner_qualified_name"] == "reviewer_structured_binding_scope"
            and event["event_type"] == "DEREFERENCE"
            and event["matched_name"] == "a[0]"
        }
        expectations = {
            "a[0] = 3;": None,
            "for (auto [a, b] : ranges[a[0]]) {": 8,
            "a[0] = 4;": None,
        }
        self.assertEqual(set(events), set(expectations))
        for line, constant in expectations.items():
            extent = self.fact(events[line], "buffer_extent_v1")
            self.assertEqual(extent["constant"], constant, line)
            if constant is None:
                self.assertEqual(extent["source"], "unknown", line)
                self.assertEqual(extent["object"]["decl"], "", line)

    def test_cpp_lambda_capture_allows_nested_array_redeclaration(self) -> None:
        self.materialize()
        relative = "src/regressions.cpp"
        lines = SOURCES[relative].splitlines()
        events = {
            lines[event["start_line"] - 1].strip(): event
            for event in self.events(relative)
            if event["owner_qualified_name"] == "reviewer_lambda_capture_nested_scope"
            and event["event_type"] == "DEREFERENCE"
        }
        expectations = {
            "[a = &a[0]] {": 8,
            "a[0] = 1;": None,
            "{ int a[4]; a[0] = 2; }": 4,
        }
        self.assertEqual(set(events), set(expectations))
        for line, constant in expectations.items():
            extent = self.fact(events[line], "buffer_extent_v1")
            self.assertEqual(extent["constant"], constant, line)
            if constant is None:
                self.assertEqual(extent["object"]["decl"], "", line)
            else:
                self.assertEqual(extent["object"]["decl"], "local:a", line)

    def test_cpp_builtin_reference_cast_preserves_outer_write(self) -> None:
        self.materialize()
        for name in ("numbers[0]", "numbers[1]"):
            event = self.event("DEREFERENCE", name, "src/regressions.cpp")
            self.assertEqual(self.fact(event, "memory_access_v1")["access"], "WRITE")

    def test_only_unqualified_or_std_memory_api_has_length_fact(self) -> None:
        self.materialize()
        relative = "src/regressions.cpp"
        lines = SOURCES[relative].splitlines()
        calls = {
            lines[event["start_line"] - 1].strip(): event
            for event in self.events(relative)
            if event["owner_qualified_name"]
            == "reviewer_scope_cast_and_memory_regressions"
            and event["event_type"] == "CALL"
        }
        custom = calls["N::memset(a, 0, 4);"]
        self.assertNotIn("memory_access_v1", custom.get("annotations", {}))
        self.assertNotIn("buffer_extent_v1", custom.get("annotations", {}))
        standard = calls["std::memset(a, 0, 4);"]
        fact = self.fact(standard, "memory_access_v1")
        self.assertEqual(fact["kind"], "memory_length")
        self.assertEqual(fact["function"], "std::memset")
        self.assertEqual(fact["expression"], "4")
        self.assertEqual(fact["unit"], "bytes")
        self.assertEqual(fact["status"], "constant")
        self.assertEqual(fact["constant"], 4)
        self.assertEqual(fact["object"]["decl"], "local:a")
        extent = self.fact(standard, "buffer_extent_v1")
        self.assertEqual(extent["constant"], 8)
        self.assertEqual(extent["bytes"]["constant"], 8)
        self.assertEqual(extent["object"]["decl"], "local:a")

    def test_cpp_memory_destination_conversion_does_not_preserve_object(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.cpp")
            if event["event_type"] == "CALL"
            and event["owner_qualified_name"] == "cpp_memory_destination_conversion"
        ]
        self.assertEqual(len(events), 3)
        lengths = {
            self.fact(event, "memory_access_v1")["constant"]:
            self.fact(event, "memory_access_v1")
            for event in events
        }
        self.assertEqual(set(lengths), {128, 256, 512})
        for size in (128, 256):
            self.assertEqual(lengths[size]["object"]["decl"], "")
            self.assertEqual(lengths[size]["object"]["storage"], "unknown")
        self.assertEqual(lengths[512]["object"]["decl"], "parameter:p")

    def test_cpp_same_named_types_do_not_lend_member_type_evidence(self) -> None:
        self.materialize()
        relative = "src/regressions.cpp"
        event = self.event("DEREFERENCE", "*(qualified_array+s.i)", relative)
        access = self.fact(event, "memory_access_v1")
        extent = self.fact(event, "buffer_extent_v1")
        self.assertEqual(access["status"], "unknown")
        self.assertIsNone(access["expression"])
        self.assertEqual(access["object"]["decl"], "")
        self.assertEqual(extent["source"], "unknown")
        self.assertIsNone(extent["constant"])
        self.assertEqual(extent["object"]["decl"], "")

        events = [
            event for event in self.events(relative)
            if event["owner_qualified_name"] == "cpp_same_named_member_types"
            and event["event_type"] in {"ALLOC", "CALL"}
            and (
                "buffer_extent_v1" in event.get("annotations", {})
                or "memory_access_v1" in event.get("annotations", {})
            )
        ]
        self.assertEqual(len(events), 2)
        allocation = next(
            event for event in events if event["event_type"] == "ALLOC"
        )
        allocation_fact = self.fact(allocation, "buffer_extent_v1")
        self.assertEqual(allocation_fact["constant"], 6144)
        self.assertEqual(allocation_fact["object"]["decl"], "")
        self.assertEqual(allocation_fact["object"]["storage"], "unknown")
        memory = next(event for event in events if event["event_type"] == "CALL")
        memory_fact = self.fact(memory, "memory_access_v1")
        self.assertEqual(memory_fact["constant"], 7168)
        self.assertEqual(memory_fact["object"]["decl"], "")
        self.assertEqual(memory_fact["object"]["storage"], "unknown")

    def test_cpp_unambiguous_direct_member_type_controls_remain_positive(self) -> None:
        self.materialize()
        relative = "src/regressions.cpp"
        access = self.access("DEREFERENCE", "member_index_array[s.index]", relative)
        self.assertEqual(access["status"], "expression")
        self.assertEqual(access["expression"], "s.index")
        self.assertEqual(access["object"]["decl"], "local:member_index_array")
        self.assertEqual(
            self.extent("DEREFERENCE", "member_index_array[s.index]", relative)["constant"],
            8,
        )

        events = [
            event for event in self.events(relative)
            if event["owner_qualified_name"] == "cpp_unambiguous_member_types"
            and event["event_type"] in {"ALLOC", "CALL"}
            and (
                "buffer_extent_v1" in event.get("annotations", {})
                or "memory_access_v1" in event.get("annotations", {})
            )
        ]
        self.assertEqual(len(events), 3)
        facts = {
            self.fact(
                event,
                "buffer_extent_v1" if event["event_type"] == "ALLOC" else "memory_access_v1",
            )["constant"]: self.fact(
                event,
                "buffer_extent_v1" if event["event_type"] == "ALLOC" else "memory_access_v1",
            )
            for event in events
        }
        self.assertEqual(set(facts), {9216, 10240, 11264})
        self.assertEqual(facts[9216]["object"]["member"], "pointer")
        self.assertEqual(facts[10240]["object"]["member"], "pointer")
        self.assertEqual(facts[11264]["object"]["member"], "data")
        for fact in facts.values():
            self.assertEqual(fact["object"]["decl"], "parameter:s")
            self.assertEqual(fact["object"]["type"], "UniqueMember")

    def test_nested_c_tag_does_not_lend_member_pointer_type(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.c")
            if event["event_type"] == "ALLOC"
            and event["owner_qualified_name"] == "shadowed_tag_member_out_argument"
        ]
        self.assertEqual(len(events), 1)
        extent = self.fact(events[0], "buffer_extent_v1")
        self.assertEqual(extent["constant"], 1024)
        self.assertEqual(extent["object"]["decl"], "")
        self.assertEqual(extent["object"]["storage"], "unknown")

    def test_unambiguous_direct_member_type_controls_remain_positive(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.c")
            if event["owner_qualified_name"] == "direct_member_value_controls"
            and event["event_type"] in {"ALLOC", "CALL"}
            and (
                "buffer_extent_v1" in event.get("annotations", {})
                or "memory_access_v1" in event.get("annotations", {})
            )
        ]
        self.assertEqual(len(events), 3)
        allocation_sizes = {2048, 4096}
        for event in events:
            key = (
                "buffer_extent_v1" if event["event_type"] == "ALLOC"
                else "memory_access_v1"
            )
            fact = self.fact(event, key)
            self.assertIn(fact["constant"], allocation_sizes | {3072})
            self.assertEqual(fact["object"]["decl"], "parameter:s")
            self.assertEqual(fact["object"]["member"], "slot")
            self.assertEqual(fact["object"]["type"], "OutHolder")

    def test_unsupported_commuted_subscript_does_not_invert_index_and_object(self) -> None:
        self.materialize()
        for event_type in ("DEREFERENCE", "WRITE"):
            event = self.event(event_type, "i[s.data]", "src/regressions.c")
            access = self.fact(event, "memory_access_v1")
            extent = self.fact(event, "buffer_extent_v1")
            self.assertEqual(access["status"], "unknown")
            self.assertIsNone(access["expression"])
            self.assertIsNone(access["constant"])
            self.assertEqual(access["object"]["decl"], "")
            self.assertEqual(access["object"]["storage"], "unknown")
            self.assertEqual(extent["source"], "unknown")
            self.assertEqual(extent["object"]["decl"], "")

    def test_identifier_commuted_subscripts_fail_closed_without_target_evidence(self) -> None:
        self.materialize()
        for matched_name in (
            "i[p]", "(i)[p]", "i[external_pointer]", "i[undeclared_target]",
        ):
            for event_type in ("DEREFERENCE", "WRITE"):
                with self.subTest(matched_name=matched_name, event_type=event_type):
                    event = self.event(event_type, matched_name, "src/regressions.c")
                    access = self.fact(event, "memory_access_v1")
                    extent = self.fact(event, "buffer_extent_v1")
                    self.assertEqual(access["status"], "unknown")
                    self.assertIsNone(access["expression"])
                    self.assertIsNone(access["constant"])
                    self.assertEqual(access["object"]["decl"], "")
                    self.assertEqual(access["object"]["storage"], "unknown")
                    self.assertEqual(extent["source"], "unknown")
                    self.assertEqual(extent["object"]["decl"], "")

    def test_parameter_array_and_pointer_subscripts_keep_orientation(self) -> None:
        self.materialize()
        commuted = self.access(
            "DEREFERENCE", "i[parameter_array]", "src/regressions.c"
        )
        self.assertEqual(commuted["expression"], "i")
        self.assertEqual(commuted["object"]["decl"], "parameter:parameter_array")
        for matched_name, declaration in (
            ("p[i]", "parameter:p"),
            ("parameter_array[i]", "parameter:parameter_array"),
        ):
            with self.subTest(matched_name=matched_name):
                access = self.access("DEREFERENCE", matched_name, "src/regressions.c")
                self.assertEqual(access["expression"], "i")
                self.assertEqual(access["status"], "expression")
                self.assertEqual(access["object"]["decl"], declaration)

    def test_cast_array_bases_do_not_reuse_declared_element_extent(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.c")
            if event["event_type"] == "DEREFERENCE" and "casted" in event["matched_name"]
        ]
        self.assertEqual(len(events), 2)
        for event in events:
            extent = self.fact(event, "buffer_extent_v1")
            self.assertEqual(extent["source"], "unknown")
            self.assertIsNone(extent["constant"])
        subscript = next(
            event for event in events
            if self.fact(event, "memory_access_v1")["kind"] == "subscript"
        )
        self.assertEqual(self.fact(subscript, "memory_access_v1")["constant"], 3)

    def test_commuted_pointer_addition_keeps_base_object_and_offset(self) -> None:
        self.materialize()
        for matched_name, declaration, extent_constant in (
            ("*(i+offset_array)", "local:offset_array", 4),
            ("*(i+p)", "parameter:p", None),
            ("*(offset_array+i)", "local:offset_array", 4),
            ("*(p+i)", "parameter:p", None),
        ):
            with self.subTest(matched_name=matched_name):
                event = self.event("DEREFERENCE", matched_name, "src/regressions.c")
                access = self.fact(event, "memory_access_v1")
                extent = self.fact(event, "buffer_extent_v1")
                self.assertEqual(access["kind"], "pointer_offset")
                self.assertEqual(access["expression"], "i")
                self.assertEqual(access["object"]["decl"], declaration)
                self.assertEqual(extent["object"]["decl"], declaration)
                self.assertEqual(extent["constant"], extent_constant)

        octal = self.access(
            "DEREFERENCE", "*(-010+offset_array)", "src/regressions.c"
        )
        self.assertEqual((octal["kind"], octal["constant"]), ("pointer_offset", -8))
        non_decimal_minimum = self.access(
            "DEREFERENCE", "*(-0x80000000+offset_array)", "src/regressions.c"
        )
        self.assertEqual(non_decimal_minimum["status"], "expression")
        self.assertIsNone(non_decimal_minimum["constant"])

    def test_member_conditional_and_unevaluated_access_direction(self) -> None:
        self.materialize()
        c_relative = "src/regressions.c"
        address = self.event("DEREFERENCE", "access_members[1]", c_relative)
        self.assertNotIn("memory_access_v1", address.get("annotations", {}))
        self.assertEqual(
            self.access("DEREFERENCE", "access_members[2]", c_relative)["access"],
            "WRITE",
        )
        self.assertEqual(
            self.access("DEREFERENCE", "access_members[3]", c_relative)["access"],
            "READ_MODIFY_WRITE",
        )

        cpp_relative = "src/regressions.cpp"
        for name in ("unevaluated[0]", "unevaluated[1]"):
            # decltype/noexcept operands are unevaluated: no structural point
            # (and therefore no value-access or extent fact) is published.
            matches = [
                event for event in self.events(cpp_relative)
                if event["event_type"] == "DEREFERENCE"
                and event["matched_name"] == name
            ]
            self.assertEqual(matches, [])
        for name in ("conditional_left[0]", "conditional_right[0]"):
            self.assertEqual(
                self.access("DEREFERENCE", name, cpp_relative)["access"], "WRITE"
            )

    def test_arrow_member_store_reads_pointer_array_element(self) -> None:
        self.materialize()
        access = self.access(
            "DEREFERENCE", "pointer_members[1]", "src/regressions.c"
        )
        self.assertEqual(access["access"], "READ")
        self.assertEqual(access["constant"], 1)
        self.assertEqual(access["object"]["decl"], "local:pointer_members")

    def test_nested_allocation_and_memory_call_object_binding(self) -> None:
        self.materialize()
        relative = "src/regressions.c"
        allocations = {
            fact["constant"]: fact
            for event in self.events(relative)
            if event["event_type"] == "ALLOC" and event["matched_name"] == "malloc"
            for fact in [self.fact(event, "buffer_extent_v1")]
            if fact["constant"] in {32, 64, 128}
        }
        for size in (32, 64):
            self.assertEqual(allocations[size]["object"]["decl"], "")
            self.assertEqual(allocations[size]["object"]["storage"], "unknown")
        self.assertEqual(allocations[128]["object"]["decl"], "parameter:p")

        copied = next(
            self.fact(event, "memory_access_v1")
            for event in self.events(relative)
            if event["event_type"] == "CALL"
            and "memory_access_v1" in event.get("annotations", {})
            and self.fact(event, "memory_access_v1")["function"] == "memcpy"
        )
        self.assertEqual(copied["constant"], 16)
        self.assertEqual(copied["object"]["decl"], "parameter:dst")
        self.assertNotEqual(copied["object"]["decl"], "parameter:r")

    def test_cast_and_addressed_memory_destinations_keep_member_identity(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.c")
            if event["event_type"] == "CALL"
            and event["owner_qualified_name"] == "cast_memory_destinations"
        ]
        self.assertEqual(len(events), 2)
        lengths = {
            self.fact(event, "memory_access_v1")["constant"]:
            self.fact(event, "memory_access_v1")
            for event in events
        }
        self.assertEqual(set(lengths), {4, 8})
        for fact in lengths.values():
            self.assertEqual(fact["object"]["decl"], "parameter:s")
            self.assertEqual(fact["object"]["member"], "data")

    def test_compound_assignment_does_not_bind_allocation_result(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.c")
            if event["event_type"] == "ALLOC"
            and event["owner_qualified_name"] == "compound_allocation_binding"
        ]
        self.assertEqual(len(events), 1)
        extent = self.fact(events[0], "buffer_extent_v1")
        self.assertEqual(extent["expression"], "32")
        self.assertEqual(extent["constant"], 32)
        self.assertEqual(extent["object"]["decl"], "")
        self.assertEqual(extent["object"]["storage"], "unknown")

    def test_indirect_assignment_does_not_bind_allocation_to_pointer_variable(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.c")
            if event["event_type"] == "ALLOC"
            and event["owner_qualified_name"] == "indirect_allocation_binding"
        ]
        self.assertEqual(len(events), 1)
        extent = self.fact(events[0], "buffer_extent_v1")
        self.assertEqual(extent["constant"], 32)
        self.assertEqual(extent["object"]["decl"], "")
        self.assertEqual(extent["object"]["storage"], "unknown")

    def test_allocation_out_argument_requires_direct_address_of_target(self) -> None:
        self.materialize()
        events = [
            event for event in self.events("src/regressions.c")
            if event["event_type"] == "ALLOC"
            and event["owner_qualified_name"] == "out_argument_allocation_binding"
        ]
        self.assertEqual(len(events), 5)
        allocations = {
            self.fact(event, "buffer_extent_v1")["constant"]:
            self.fact(event, "buffer_extent_v1")
            for event in events
        }
        self.assertEqual(set(allocations), {32, 64, 128, 256, 512})
        for size in (32, 256):
            self.assertEqual(allocations[size]["object"]["decl"], "parameter:p")
        for size in (64, 128, 512):
            self.assertEqual(allocations[size]["object"]["decl"], "")
            self.assertEqual(allocations[size]["object"]["storage"], "unknown")

    def test_existing_positive_defect_output_does_not_consume_new_facts(self) -> None:
        defect_root = Path(self.temp.name) / "defect_repo"
        write(
            defect_root / "src/double.c",
            "int f(int n) {\n"
            "    char *p = malloc(64);\n"
            "    if (!p) return -1;\n"
            "    free(p);\n"
            "    free(p);\n"
            "    return n;\n"
            "}\n",
        )
        defect_db = Path(self.temp.name) / "defect.db"
        full_index(defect_root, defect_db)
        analyze_scope(defect_root, "src", ("defect",), database=defect_db)
        before = query_defect_candidates(
            defect_root, defect_type="double_free", database=defect_db
        )
        self.assertEqual(before["status"], "available", before.get("reason"))
        self.assertEqual(len(before["candidates"]), 1)

        def strip_new_facts(value):
            if isinstance(value, dict):
                value.pop("buffer_extent_v1", None)
                value.pop("memory_access_v1", None)
                for child in value.values():
                    strip_new_facts(child)
            elif isinstance(value, list):
                for child in value:
                    strip_new_facts(child)

        with closing(sqlite3.connect(defect_db)) as connection:
            rows = connection.execute(
                "SELECT analysis_node_id, payload FROM analysis_nodes "
                "WHERE feature IN ('sparse_cfg:cpp', 'sparse_dfg:cpp')"
            ).fetchall()
            for node_id, payload in rows:
                decoded = json.loads(payload)
                strip_new_facts(decoded)
                connection.execute(
                    "UPDATE analysis_nodes SET payload=? WHERE analysis_node_id=?",
                    (json.dumps(decoded, sort_keys=True, separators=(",", ":")), node_id),
                )
            connection.commit()
        after = query_defect_candidates(
            defect_root, defect_type="double_free", database=defect_db
        )
        self.assertEqual(after, before)

    def test_default_l1_index_has_no_derived_buffer_facts(self) -> None:
        result = query_analysis(
            self.root, "sparse_cfg", file_path="src/facts.c", database=self.database
        )
        self.assertNotEqual(result["status"], "available")
        with closing(sqlite3.connect(self.database)) as connection:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_nodes'"
            ).fetchone()
            count = 0 if table is None else connection.execute(
                "SELECT COUNT(*) FROM analysis_nodes "
                "WHERE feature IN ('sparse_cfg:cpp', 'sparse_dfg:cpp')"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_repeat_and_forced_rebuild_are_byte_stable(self) -> None:
        first = self.materialize()
        self.assertIn("src/facts.c", first["features"]["sparse_cfg"]["materialized"])
        before = json.dumps(self.events(), sort_keys=True, separators=(",", ":"))
        memory_before = json.dumps(
            self.events("src/memory_destinations.c"), sort_keys=True, separators=(",", ":")
        )
        second = self.materialize()
        self.assertIn("src/facts.c", second["features"]["sparse_cfg"]["reused"])
        self.assertEqual(before, json.dumps(self.events(), sort_keys=True, separators=(",", ":")))
        self.assertEqual(
            memory_before,
            json.dumps(
                self.events("src/memory_destinations.c"), sort_keys=True, separators=(",", ":")
            ),
        )

        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "UPDATE analysis_state SET feature_version=5 "
                "WHERE feature='sparse_cfg:cpp' AND file_id IN "
                "(SELECT file_id FROM files WHERE path IN "
                "('src/facts.c', 'src/memory_destinations.c'))"
            )
            connection.commit()
        stale = query_analysis(
            self.root, "sparse_cfg", file_path="src/facts.c", database=self.database
        )
        self.assertEqual(stale["status"], "stale")
        self.materialize()
        self.assertEqual(before, json.dumps(self.events(), sort_keys=True, separators=(",", ":")))
        self.assertEqual(
            memory_before,
            json.dumps(
                self.events("src/memory_destinations.c"), sort_keys=True, separators=(",", ":")
            ),
        )

    def test_source_change_invalidates_and_recomputes_extent(self) -> None:
        self.materialize()
        path = self.root / "src/facts.c"
        path.write_text(path.read_text().replace("char buf[64];", "char buf[65];", 1))
        memory_path = self.root / "src/memory_destinations.c"
        memory_path.write_text(
            memory_path.read_text().replace("char dst[4];", "char dst[6];", 1)
        )
        incremental_update(self.root, self.database)
        for relative in ("src/facts.c", "src/memory_destinations.c"):
            stale = query_analysis(
                self.root, "sparse_cfg", file_path=relative, database=self.database
            )
            self.assertEqual(stale["status"], "stale", relative)
        self.materialize()
        self.assertEqual(self.extent("DEREFERENCE", "buf[n-1]")["constant"], 65)
        golden = next(
            event for event in self.events("src/memory_destinations.c")
            if event["owner_qualified_name"] == "memory_destination_golden"
            and event["event_type"] == "CALL"
        )
        self.assertEqual(self.fact(golden, "buffer_extent_v1")["constant"], 6)

    def test_scfg_version_and_dfg_dependency_freshness(self) -> None:
        self.assertEqual(ANALYZER_VERSIONS["sparse_cfg:cpp"], 14)
        self.assertEqual(ANALYZER_VERSIONS["sparse_dfg:cpp"], 4)
        self.assertEqual(ANALYZER_VERSIONS["events:cpp"], 3)
        self.materialize("sparse_dfg")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT metadata FROM analysis_state WHERE feature='sparse_dfg:cpp' "
                "AND file_id IN (SELECT file_id FROM files WHERE path='src/facts.c')"
            ).fetchone()
            metadata = json.loads(row["metadata"])
            metadata["dependencies"]["sparse_cfg:cpp"] = "cpp-sparse_cfg-v9"
            connection.execute(
                "UPDATE analysis_state SET metadata=? WHERE feature='sparse_dfg:cpp' "
                "AND file_id IN (SELECT file_id FROM files WHERE path='src/facts.c')",
                (json.dumps(metadata, sort_keys=True),),
            )
            connection.commit()
        stale = query_analysis(
            self.root, "sparse_dfg", file_path="src/facts.c", database=self.database
        )
        self.assertEqual(stale["status"], "stale")
        self.assertIn("dependency_changed", stale["reason"])
        self.materialize("sparse_dfg")
        current = query_analysis(
            self.root, "sparse_dfg", file_path="src/facts.c", database=self.database
        )
        self.assertEqual(current["status"], "available", current.get("reason"))
        with closing(sqlite3.connect(self.database)) as connection:
            version = connection.execute(
                "SELECT feature_version FROM analysis_state WHERE feature='sparse_dfg:cpp' "
                "AND file_id IN (SELECT file_id FROM files WHERE path='src/facts.c')"
            ).fetchone()[0]
        self.assertEqual(version, 4)

    def test_oob_shaped_array_access_is_only_a_b2_candidate(self) -> None:
        # #82 froze the facts when no bounds query existed. B2 (#93) now
        # consumes them: the fixture yields exactly the two write-direction
        # candidates and no unrelated family.
        clean_root = Path(self.temp.name) / "clean_repo"
        write(
            clean_root / "src/clean.c",
            "void clean(void) { char a[4]; a[4] = 0; memset(a, 0, 8); }\n",
        )
        clean_db = Path(self.temp.name) / "clean.db"
        full_index(clean_root, clean_db)
        analyze_scope(clean_root, "src", ("defect",), database=clean_db)
        result = query_defect_candidates(clean_root, database=clean_db)
        self.assertEqual(result["status"], "available", result.get("reason"))
        self.assertEqual(
            {candidate["defect_key"] for candidate in result["candidates"]},
            {"oob_write"})
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(
            sorted(candidate["metadata"]["access_kind"]
                   for candidate in result["candidates"]),
            ["memory_length", "subscript"])


if __name__ == "__main__":
    unittest.main()
