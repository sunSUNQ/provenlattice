# Evidence Scope V1

The Blind View is an entry point, not an evidence boundary. Within the frozen source repositories, read-only same-file and cross-file navigation, declaration and definition lookup, owner and namespace lookup, include tracing, necessary type propagation, candidate source verification, and allowed frozen Build Context inspection are permitted.

When those permitted sources uniquely establish a target, the absence of the complete chain in the Blind View does not justify `INSUFFICIENT_EVIDENCE`. Use that verdict only when the matter remains undeterminable after the permitted evidence has been used. Do not use network sources, unfrozen artifacts, system predictions, or other annotator material.
