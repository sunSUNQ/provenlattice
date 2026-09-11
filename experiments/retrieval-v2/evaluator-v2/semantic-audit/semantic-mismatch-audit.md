# T01/T03 Blind Semantic Audit

## T01 — Document to Code

- Original Ground Truth required `brpc.policy.AddServersInBatch.replicas` and the cpp path.
- The prompt describes `c_murmurhash_bl`, whose core implementation is
  `ConsistentHashingBoundedLoadBalancer` (`E-CODE-1726...`) and its bounded-load selection logic.
- The local `replicas` variable is an implementation detail, not the main bounded-load symbol.
- Verdict: the class evidence is a **VALID ACCEPTABLE ALTERNATIVE**; cells that returned it were
  evaluator false negatives under V1. Cells that did not establish the bounded-load concept remain
  true capability failures.

## T03 — Code to Document

- Original Ground Truth required the `client.md` c_murmurhash_bl section.
- The symbol is the virtual-node staging vector; the authoritative design explanation is
  `docs/cn/consistent_hashing.md`, especially `虚拟节点个数` and `实现方式`.
- Verdict: the consistent-hashing document is a **VALID ACCEPTABLE ALTERNATIVE**. Two R2.1
  CodeGraph cells and one Native cell became evaluator false negatives under the V1 section match.

The review was performed from prompt, candidate output, cited Evidence IDs and source locations;
Arm labels were not used to decide validity. Original scores remain immutable.
