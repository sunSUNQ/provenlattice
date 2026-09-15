# CALLS_V1 Macro Semantics

CALLS_V1 operates at the preprocessor-before source layer. A macro invocation observable as a source-level call expression is a CALLS relation. This rule applies uniformly to assertion, expectation, and other macro invocations.

Do not require expansion before recognising the relation. Do not treat a macro invocation as relation-absent merely because it is a macro, and do not use a function inside a hypothetical expansion as the target of the source-level CALLS relation.
