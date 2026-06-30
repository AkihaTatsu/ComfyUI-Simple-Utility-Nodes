# Simple Global Loop Node Fix History

Date: 2026-07-01

This document records the loop-node debugging work done for `ComfyUI-Simple-Utility-Nodes`, including the observed bugs, attempted fixes, outcomes, and current unresolved state.

Reference workflow:

```text
/mnt/SSD-Share01/ComfyUI/user/default/workflows/Workflow - NSFW 03 - Video 05.json
```

Primary implementation file:

```text
global_nodes/loop_nodes.py
```

Current git state note: `global_nodes/loop_nodes.py` is currently untracked in this working tree, so `git diff -- global_nodes/loop_nodes.py` does not show its content unless the file is added or compared manually.

## Current Status

The loop-node fix is not complete.

The latest user-visible report is that the previous fix still has the serious runtime problem:

- Skip behavior still does not reliably behave like a normal bypass in the real workflow.
- Active loop behavior still does not reliably carry updated values from one iteration to the next in the real workflow.
- There remains a high risk that some attempted skip/passthrough mechanism is still interacting badly with ComfyUI dynamic graph scheduling.

Important distinction:

- Synthetic unit-style tests passed for several simplified cases.
- The real workflow still fails according to user feedback.
- Therefore the synthetic tests are insufficient and must not be treated as proof of correctness.

## Original Goals

The intended loop-node behavior was:

- `For Loop` should allow `total=0`.
- `For total=0` should skip the loop body and pass Start `initial_valueN` directly to End `valueN`.
- `While Loop` should support an equivalent skip path when the Start condition is statically false.
- Active loops should feed updated End values into the next Start iteration.
- The loop should avoid memory explosion by passing large objects by evaluated reference, like a lightweight reroute.
- Internal generated loop nodes must not be externally loadable or incorrectly pulled into the outer graph.
- The previous severe bug where upstream dependencies rerun from the beginning after one loop iteration must not return.

## Bug 1: Loop Completion Caused Upstream Rerun

Symptom:

- After one loop iteration completed, upstream parts of the workflow appeared to run again from the start.
- This repeatedly returned after skip/passthrough mechanisms were added.

Suspected cause:

- Returning dynamic result links from normal completion paths can cause ComfyUI to add strong links and schedule link sources again.
- ComfyUI treats subgraph expansion results specially:
  - `{"result": links, "expand": graph}` asks the executor to resolve linked outputs after scheduling those links.
  - This is valid for generated subgraphs but dangerous if used to return links from the original upstream graph during normal loop completion.

Attempted fixes:

- Avoid returning dynamic links on normal complete.
- Return evaluated `kwargs` values from End when the loop finishes.
- Only use dynamic result links in skip passthrough.

Outcome:

- This is theoretically the correct direction.
- Synthetic tests confirmed complete paths return tuples, not expand dicts.
- Real workflow still has issues, so this cannot be considered fully successful.

Current lesson:

- Any future fix must keep this invariant:

```text
Normal complete path must return evaluated values only.
Normal continue path must inject evaluated objects only.
Dynamic link passthrough must not be reused for active loop completion.
```

## Bug 2: Skip Path Ended the Workflow Instead of Bypassing

Symptom:

- When the loop should skip, the workflow effectively stopped instead of continuing with passthrough output.
- In the reference workflow, node `1385` is `SimpleGlobalForLoopStart`, node `1430` is `SimpleGlobalForLoopEnd`.
- The reference workflow was observed with `For Start total=0`.

Relevant log evidence:

```text
[2026-06-30 23:33:21.765] [Global-Loop-Node] For Start execute: display_id='1385', index=0, total=0.
[2026-06-30 23:42:07.281] [Global-Loop-Node] For Start execute: display_id='1385', index=0, total=0.
```

At that stage, the End passthrough log did not appear, which suggested End was not executing.

Likely cause:

- Start returned `ExecutionBlocker` on body outputs when `total=0`.
- End still had non-lazy `initial_valueN` body inputs.
- ComfyUI therefore tried to resolve blocked body inputs before End could run.
- End itself became blocked, so passthrough could not happen.

Attempted fix:

- Make `ForLoopEnd.initial_valueN` lazy.
- Make `check_lazy_status()` return `[]` when `total<=0`.
- Keep Start's blocker outputs to prevent body execution.
- Let End skip branch return Start `initial_valueN`.

Partial outcome:

- Later logs showed the End skip branch did execute:

```text
[2026-07-01 00:10:53.574] [Global-Loop-Node] For Start execute: display_id='1385', index=0, total=0.
[2026-07-01 00:10:53.580] [Global-Loop-Node] For End state: open_display_id='1385', close_display_id='1430', current_index=0, next_index=1, total=0, continue=False.
[2026-07-01 00:10:53.580] [Global-Loop-Node] For End passthrough: close_display_id='1430', total=0, loop body blocked.
```

But user feedback says the problem still exists.

Conclusion:

- The lazy-End blocker issue was probably real and partially fixed.
- It is not the full bug.
- The current passthrough implementation may still be incompatible with the real downstream graph or ComfyUI scheduling behavior.

## Bug 3: Active Loop Reused Initial Inputs Instead of Updated Values

Symptom:

- The loop iterated, but each iteration appeared to receive the original Start input and produce results based on the initial state.
- Updated data from the loop body did not reliably become the next iteration's input.

Intended behavior:

- For each carried slot:

```text
Start.valueN -> body -> End.initial_valueN -> next Start.initial_valueN
```

Attempted fix:

- On continue, build `carried_values` from End runtime `kwargs`, not from Start's original prompt links.
- Inject those evaluated values into the cloned Start node.

Current code shape:

```python
carried_values = {"initial_value0": next_index}
for i in range(1, MAX_FLOW_NUM):
    carried_values[f"initial_value{i}"] = kwargs.get(f"initial_value{i}", None)
```

Synthetic outcome:

- Tests confirmed that a simplified expanded Start receives the same object passed into End `kwargs`, not the original source link.

Real outcome:

- User reports the issue remains.

Conclusion:

- Either the synthetic test does not match real ComfyUI execution closely enough, or the body-node collection/cloning logic is wrong for the reference workflow.
- Particular suspicion: `collect_body_nodes()` may not include the intended body nodes in some real graph layouts, especially with reroutes, output nodes, multi-output nodes, or nodes connected to both inside and outside the loop.

## Bug 4: Body Collection May Be Incorrect

Observed reference workflow structure:

```text
1385 SimpleGlobalForLoopStart
1430 SimpleGlobalForLoopEnd
1383 ImageBatchMulti: Start.value1 -> ImageBatchMulti -> End.initial_value1
1558/1559 Reroute chain around carried latent/value2
1443 ImageBatchMulti and 1691 WanAdvancedExtractLastImages downstream of End
1663 WanAdvancedExtractLastImages downstream of Start.value1
```

Important discovery:

- A simplified closure walk earlier found only Start and End as contained nodes in one pass.
- That suggests the body collection algorithm may fail to identify nodes between Start and End in at least some graph shapes.

Why this matters:

- If the loop body is not cloned correctly, then continuation will not run the actual intended body.
- If external downstream nodes are accidentally included, the generated graph can become too large or schedule wrong dependencies.
- If body nodes are excluded, the next iteration may effectively reuse stale values or bypass computation.

Current body collection method:

- Recursively explores dependencies upstream from End.
- Collects descendants reachable from Start within that upstream map.
- Special-cases output nodes.

Risk:

- This algorithm is fragile.
- It depends on the exact direction of graph traversal and may break with reroutes, partial external links, or nodes that are both loop-internal and externally consumed.

Status:

- Not proven correct.
- Likely still a source of the remaining real-workflow failure.

## Bug 5: While Loop Needed the Same Full Patch

Symptom / requirement:

- The same skip, passthrough, carried-value, and anti-rerun rules must apply to `While Loop`.

Attempted fix:

- `WhileLoopStart.initial_valueN` made non-lazy.
- `WhileLoopEnd.initial_valueN` kept lazy.
- Static false Start condition makes End `check_lazy_status()` return `[]`.
- Static false skip uses the same Start-to-End passthrough helper.
- Continue injects evaluated End `kwargs` into the next cloned Start.

Important limitation:

- If While Start `condition` is linked, End cannot reliably know that runtime condition during lazy dependency selection.
- Linked false Start conditions therefore kept blocker-style behavior instead of full passthrough.

Outcome:

- Synthetic tests passed.
- Real-workflow correctness is not proven.

## Bug 6: Skip Passthrough May Still Be Conceptually Unsafe

Current skip passthrough helper:

```python
def _skip_passthrough_result(results):
    if any(is_link(value) for value in results):
        return {"result": results, "expand": {}}
    return results
```

Reason it was added:

- If Start `initial_valueN` is linked and the loop body is skipped, End needs a way to make its output resolve to Start's upstream input without evaluating the body.

Risk:

- Even with empty `expand`, returning original graph links may still make ComfyUI add strong links and schedule sources in a way that differs from normal node execution.
- This was deliberately limited to skip branches, but the real workflow may still be sensitive to it.

Status:

- Not proven safe in the full workflow.
- Needs deeper validation against ComfyUI's `pending_subgraph_results` and `ExecutionList.add_strong_link()` behavior.

## Bug 7: Tests Were Too Synthetic

Tests performed:

- Python AST parse for `loop_nodes.py`.
- JSON parse for `tooltips.json`.
- Direct method calls for:
  - For skip passthrough.
  - For complete.
  - For continue.
  - While skip passthrough.
  - While complete.
  - While continue.
  - Object identity preservation.

Why they were insufficient:

- They did not run through the real ComfyUI executor scheduling loop.
- They did not validate `ExecutionList` strong-link behavior.
- They did not validate cache behavior.
- They did not validate the full reference workflow graph.
- They did not validate body collection under real reroute/mixed inside-outside graph conditions.

Conclusion:

- Future validation must use either ComfyUI's execution test harness or a real minimal workflow executed by ComfyUI, not only direct method calls.

## Attempt Timeline

### 1. Initial Loop Nodes Added

Change:

- Added `SimpleGlobalForLoopStart`, `SimpleGlobalForLoopEnd`, `SimpleGlobalWhileLoopStart`, `SimpleGlobalWhileLoopEnd`.
- Used ComfyUI `GraphBuilder` to clone loop body and recurse.
- Added dynamic frontend slots in `web/global_nodes.js`.

Outcome:

- Basic loop concept existed.
- Several execution semantics were not yet correct.

### 2. Index Numbering Fix

Change:

- For and While visible indices were adjusted to start at `1`.
- Internal `initial_value0` was used as zero-based loop state.

Outcome:

- Conceptually correct.
- Not the source of the current severe bug.

### 3. Reroute-Style Memory Fix

Change:

- Avoided separately caching large carried objects.
- Attempted to pass IMAGE/LATENT/MODEL values as object references across iterations.

Outcome:

- Direction is still required.
- Must be preserved.
- But this alone does not guarantee correct scheduling.

### 4. Skip Mechanism Added

Change:

- For `total=0`, Start returned `ExecutionBlocker` on body-facing outputs.
- End attempted to passthrough Start initial values.
- While static false followed similar behavior.

Outcome:

- Introduced or exposed workflow-ending behavior because End could be blocked by non-lazy body inputs.

### 5. Attempts to Prevent Upstream Rerun

Change:

- Removed dynamic result returns from normal completion.
- Kept dynamic result only for skip passthrough.

Outcome:

- The rule is still important.
- The real bug persisted.

### 6. Restoring Skip After Removing It

Change:

- Skip mechanism was temporarily removed or simplified during debugging.
- User required preserving reroute memory behavior.
- Later skip was reintroduced with blocker style inspired by Easy Use, but without relying on Easy Use's problematic paths.

Outcome:

- Did not fully resolve the real workflow issue.

### 7. Latest Patch

Change:

- `For/While Start.initial_valueN` made strong inputs.
- `For/While End.initial_valueN` made lazy inputs.
- Continue paths inject evaluated `kwargs` values.
- Complete paths return evaluated tuples only.
- Skip-only helper renamed/commented to avoid accidental normal-path use.

Synthetic outcome:

- Direct tests passed.

Real outcome:

- User reports the issue still exists.
- Therefore the latest patch is insufficient.

## Known Logs and Observations

Relevant log snippets:

```text
[2026-06-30 23:15:33.659] [Global-Loop-Node] For Start execute: display_id='1385', index=0, total=1.
[2026-06-30 23:25:03.344] [Global-Loop-Node] For Start execute: display_id='1385', index=0, total=1.
[2026-06-30 23:33:21.765] [Global-Loop-Node] For Start execute: display_id='1385', index=0, total=0.
[2026-06-30 23:42:07.281] [Global-Loop-Node] For Start execute: display_id='1385', index=0, total=0.
[2026-07-01 00:10:53.574] [Global-Loop-Node] For Start execute: display_id='1385', index=0, total=0.
[2026-07-01 00:10:53.580] [Global-Loop-Node] For End state: open_display_id='1385', close_display_id='1430', current_index=0, next_index=1, total=0, continue=False.
[2026-07-01 00:10:53.580] [Global-Loop-Node] For End passthrough: close_display_id='1430', total=0, loop body blocked.
```

Interpretation:

- Earlier versions did not always reach End when skipping.
- Later version reached End skip branch.
- The remaining failure is likely after or around passthrough resolution, downstream scheduling, or body collection for active loops.

## Current Invariants That Should Not Be Broken

These constraints were learned through repeated failures:

- Do not return original upstream links from normal complete.
- Do not return `{"expand": ...}` from normal complete.
- Do not read carried values for the next iteration from the original Start prompt inputs.
- Continue must use End runtime `kwargs`.
- Large carried objects must be passed as references, not copied or serialized.
- End body inputs must be lazy when skip is possible.
- Start carried inputs should be strong so active loops receive concrete current values.
- Skip body outputs may use `ExecutionBlocker`, but End must not depend on blocked body inputs in skip mode.

## Current High-Risk Areas

### 1. `collect_body_nodes()`

Risk:

- It may collect too few nodes, too many nodes, or the wrong nodes.
- The reference workflow has reroutes and nodes consumed by both loop-internal and external downstream nodes.

Needed validation:

- Log and inspect contained nodes for the real workflow when `total>1`.
- Confirm `ImageBatchMulti` and the reroute chain feeding End are included.
- Confirm downstream nodes after End are not included in the recursive body.

### 2. Skip passthrough via empty expand

Risk:

- `{"result": original_links, "expand": {}}` may still have scheduling side effects.

Needed validation:

- Test with ComfyUI executor, not direct function calls.
- Confirm downstream nodes receive End outputs and continue executing.
- Confirm upstream source is scheduled only as needed and not repeatedly.

### 3. Cache interactions

Risk:

- ComfyUI output cache and subcache behavior may be different for ephemeral nodes.
- A direct method test does not exercise `pending_subgraph_results`, `cache_link`, or `add_strong_link`.

Needed validation:

- Use a counter node in a real ComfyUI execution test.
- Verify source execution count across `total=0`, `total=1`, and `total=2`.

## Recommended Next Debugging Plan

Do not make another speculative loop patch first.

Next steps should be:

1. Build a minimal ComfyUI execution test workflow using real executor scheduling.
2. Add a tiny counter/source node or use existing ComfyUI testing nodes if available.
3. Reproduce three cases:
   - `For total=0`: downstream receives Start initial value and body counter stays zero.
   - `For total=2`: body counter runs twice and the second iteration receives first iteration output.
   - `For total=2`: upstream initial source runs once, not once per iteration.
4. Add equivalent While cases.
5. Instrument `collect_body_nodes()` for the reference workflow and record contained nodes.
6. Only after reproducing the failure in a minimal executor test, change implementation.

## Open Questions

- Is the remaining failure specifically in skip mode, active loop mode, or both in the latest run?
- Does the latest real failure show `For End passthrough`, `For End expand`, or neither?
- For active loops, does `Body collect` include the actual body nodes in the reference workflow?
- Does ComfyUI treat empty `expand` with linked `result` as a subgraph result that can still cause unintended strong-link scheduling?
- Is the frontend dynamic-slot ordering producing prompt inputs that do not match backend assumptions for some saved workflows?

## Final Assessment

The repeated failures were caused by treating ComfyUI dynamic graph execution as if direct Python method tests were enough. They are not.

The most important surviving facts are:

- The complete path must never reintroduce dynamic upstream links.
- The continue path must only use evaluated End values.
- The skip path still needs a safe bridge mechanism, but the current empty-expand link bridge is not proven correct in the real executor.
- The body collection algorithm is a major unresolved risk.
- The next fix should start from a real executor-level reproduction, not another isolated helper-level patch.

## Removal on 2026-07-01

All Simple Global Loop Node runtime integration was removed from the extension after the latest report that the severe workflow bug still exists.

Removed backend pieces:

- Deleted `global_nodes/loop_nodes.py`.
- Removed `.loop_nodes` imports from `global_nodes/__init__.py`.
- Removed loop node mappings from the exported `NODE_CLASS_MAPPINGS`.
- Removed loop node mappings from the exported `NODE_DISPLAY_NAME_MAPPINGS`.

Removed frontend pieces:

- Removed loop node names from the Global-node pale-blue styling branch in `web/global_nodes.js`.
- Removed dynamic carried-slot frontend logic for:
  - `SimpleGlobalForLoopStart`
  - `SimpleGlobalForLoopEnd`
  - `SimpleGlobalWhileLoopStart`
  - `SimpleGlobalWhileLoopEnd`
- Removed the frontend behavior that added `initial_valueN` inputs and `valueN` outputs on demand up to 19 slots.
- Removed flow-slot shape handling for these loop nodes.

Removed public documentation:

- Removed the `Simple Global Loop Nodes` section from `README.md`.
- Removed tooltip entries for all four loop nodes from `tooltips.json`.

Important consequence:

- Existing workflows containing these node class names will now load them as missing custom nodes until a replacement implementation is created or the workflow is migrated.

## Removed Design Details

The removed design exposed four node classes:

```text
SimpleGlobalForLoopStart
SimpleGlobalForLoopEnd
SimpleGlobalWhileLoopStart
SimpleGlobalWhileLoopEnd
```

Display names:

```text
⛏️ Simple Global For Loop Start
⛏️ Simple Global For Loop End
⛏️ Simple Global While Loop Start
⛏️ Simple Global While Loop End
```

Shared constants:

```text
MAX_FLOW_NUM = 20
ANY_TYPE = "*"
FLOW_TYPE = "FLOW_CONTROL"
```

For Start intended interface:

```text
Inputs:
- total: INT, default 1, min 0, max 100000
- initial_value1..initial_value19: *
- hidden initial_value0: internal loop index
- hidden dynprompt
- hidden unique_id
- hidden extra_pnginfo

Outputs:
- flow: FLOW_CONTROL
- index: INT
- value1..value19: *
```

For End intended interface:

```text
Inputs:
- flow: FLOW_CONTROL with rawLink
- initial_value1..initial_value19: *, lazy in the latest attempt
- hidden dynprompt
- hidden unique_id
- hidden extra_pnginfo

Outputs:
- value1..value19: *
```

While Start intended interface:

```text
Inputs:
- condition: BOOLEAN, default true
- initial_value1..initial_value19: *
- hidden initial_value0: internal loop index
- hidden dynprompt
- hidden unique_id

Outputs:
- flow: FLOW_CONTROL
- index: INT
- value1..value19: *
```

While End intended interface:

```text
Inputs:
- flow: FLOW_CONTROL with rawLink
- condition: BOOLEAN, lazy in the latest attempt
- initial_value1..initial_value19: *, lazy in the latest attempt
- hidden dynprompt
- hidden unique_id
- hidden extra_pnginfo

Outputs:
- value1..value19: *
```

Intended normal For behavior:

```text
current_index = Start.initial_value0 or 0
visible_index = current_index + 1
next_index = current_index + 1
continue = next_index < total

If total > 0:
    Start.valueN = Start.initial_valueN
If End continue is false:
    End.valueN = evaluated End.initial_valueN
If End continue is true:
    clone loop body
    inject initial_value0 = next_index into cloned Start
    inject initial_valueN = evaluated End.initial_valueN into cloned Start
```

Intended normal While behavior:

```text
current_index = Start.initial_value0 or 0
visible_index = current_index + 1

If Start.condition is true:
    Start.valueN = Start.initial_valueN
If End.condition is false:
    End.valueN = evaluated End.initial_valueN
If End.condition is true:
    clone loop body
    inject initial_value0 = current_index + 1 into cloned Start
    inject initial_valueN = evaluated End.initial_valueN into cloned Start
```

Intended skip behavior:

```text
For total = 0:
    Start.index and Start.valueN return ExecutionBlocker(None)
    End.check_lazy_status returns []
    End.valueN should passthrough Start.initial_valueN

While static Start.condition = false:
    Start.index and Start.valueN return ExecutionBlocker(None)
    End.check_lazy_status returns []
    End.valueN should passthrough Start.initial_valueN

While linked Start.condition = false:
    The removed design did not have a safe complete passthrough.
    It kept blocker-style behavior because End could not know the linked runtime condition during lazy scheduling.
```

Removed skip passthrough helper:

```python
def _skip_passthrough_result(results):
    if any(is_link(value) for value in results):
        return {"result": results, "expand": {}}
    return results
```

Reason it was removed:

- It was not proven safe in the real ComfyUI executor.
- Even with `expand = {}`, linked results may still create strong-link scheduling behavior that differs from a normal bypass.

Removed loop body cloning design:

```text
1. Starting from the End node, recursively explore linked dependencies.
2. Build an upstream map.
3. Collect descendants reachable from the Start node inside that upstream map.
4. Always include Start and End.
5. Clone contained nodes with GraphBuilder.
6. Rename cloned End to "Recurse" to avoid exponentially growing IDs.
7. Keep internal links pointing to cloned nodes.
8. Keep external links pointing to original external nodes.
9. Override cloned Start carried inputs with evaluated End values.
10. Return cloned End outputs as dynamic result links.
```

Reason it was removed:

- The body collector was not proven correct for real workflows with reroutes, mixed internal/external consumers, and output nodes.
- A previous inspection suggested it could collect only Start and End in a graph where body nodes should have been included.
- Incorrect body collection can explain both stale carried values and repeated upstream execution.

Removed memory strategy:

```text
Do not serialize, copy, or separately cache carried IMAGE/LATENT/MODEL values.
Carry evaluated Python object references from End kwargs into the cloned Start.
This was intended to behave like a lightweight reroute and avoid memory explosion.
```

This strategy is still desirable for a future replacement, but it must be validated through ComfyUI executor-level tests.

Removed frontend dynamic-slot design:

```text
maxSlots = 19

Start nodes:
- first dynamic input index: 0
- first dynamic output index: 2

End nodes:
- first dynamic input index: 1
- first dynamic output index: 0

When all visible value inputs or outputs were connected:
- add initial_value{N+1}
- add value{N+1}

When trailing value inputs or outputs were disconnected:
- remove the trailing paired input/output when safe
```

Known frontend risk:

- Saved workflows may preserve dynamic slots in ways that do not exactly match backend assumptions.
- Future designs should prefer a backend-native dynamic input pattern or a simpler fixed-slot interface unless executor-level tests cover saved workflow reloads.

## Requirements for Any Future Replacement

A replacement loop design should not be added back until it has executor-level tests for all of these cases:

- `For total=0` skips body and downstream nodes still execute.
- `For total=1` runs body once and completes without dynamic upstream rerun.
- `For total=2` runs body twice and the second iteration receives the first iteration's output.
- `While static false` skips body and downstream nodes still execute.
- `While true then false` runs once and returns updated values.
- Initial upstream source executes once for active loops, not once per iteration.
- Body node executes exactly once per iteration.
- Large carried objects preserve identity or at least avoid extra copies.
- Body collection includes actual internal body nodes and excludes downstream nodes after End.
- Workflows with reroutes and multi-output nodes behave correctly.
- Existing workflows with missing removed loop nodes have a documented migration path before reintroducing node names.
