# LoopStep

The `LoopStep` provides powerful iteration capabilities within a PIL workflow, allowing for repeated execution of a sequence of steps. It supports several types of loops based on the expression provided.

## Common Attributes

*   `def: <variable_name>` (Optional): If provided, the `LoopStep` will collect the output of the *last step executed within each iteration* into a list, and this list will be stored in the context under `<variable_name>`. If `def` is not provided, the loop executes for its side effects, and no aggregated result is stored from the loop itself.
*   `steps: List[StepType]`: A mandatory list of PIL steps that will be executed in each iteration of the loop.

## Loop Types and Syntax

The type of loop is determined by the main expression key used for the `LoopStep`: `for`, `while`, or `loop` (which often acts as an alias for `while` or is parsed based on its content).

### 1. For-Each Loop (Iterating over a Collection)

Iterates over each item in a specified collection (list or other iterable) from the PIL context.

**Syntax:**

```yaml
- for: <loop_var> in {{<collection_var>}}
  def: <output_list_var> # Optional
  steps:
    - ... # Steps to execute for each item
    - ...
```

*   `<loop_var>`: The name of the variable that will hold the current item from the collection in each iteration. This variable is available in the context of the `steps` within the loop.
*   `{{<collection_var>}}`: A template expression resolving to a list or iterable variable in the PIL context.
*   **Context Scoping**: For each iteration, a new, isolated sub-context is created for the loop's `steps`. This sub-context inherits from the parent context an_pd contains the current `<loop_var>`. Changes made to variables within one iteration (other than the `<loop_var>` itself if it were a mutable object passed by reference from the collection) do not affect other iterations or the parent context directly after the loop, unless explicitly passed out (which is not a direct feature of `LoopStep` for variables other than the aggregated output via `def`).

**Example:**

```yaml
input:
  vars:
    my_items: list

workflow:
  steps:
    - code:
        lang: python
        script: "result = ['apple', 'banana', 'cherry']"
        def: my_items

    - for: item in {{my_items}}
      def: processed_item_names
      steps:
        - prompt:
            text: "Describe the fruit: {{item}}"
            def: item_description # This will be the value collected by 'processed_item_names'
```
In this example, `processed_item_names` will be a list containing the descriptions for "apple", "banana", and "cherry".

### 2. For-Range Loop (Iterating over a Numerical Range)

Iterates a specified number of times, similar to Python's `range()` function.

**Syntax:**

```yaml
- for: <loop_var> in range(<stop>)
  def: <output_list_var> # Optional
  steps:
    - ...

# or
- for: <loop_var> in range(<start>, <stop>)
  def: <output_list_var> # Optional
  steps:
    - ...

# or
- for: <loop_var> in range(<start>, <stop>, <step_val>)
  def: <output_list_var> # Optional
  steps:
    - ...
```

*   `<loop_var>`: The name of the variable that will hold the current integer from the range in each iteration.
*   `range(...)`: The arguments `<start>`, `<stop>`, `<step_val>` can be:
    *   Literal integers (e.g., `range(5)`, `range(1, 5)`, `range(0, 10, 2)`).
    *   Template variables resolving to integers (e.g., `range({{max_count}})`, `range({{start_index}}, {{end_index}})`).
*   **Context Scoping**: Similar to the for-each loop, each iteration has an isolated sub-context with the current `<loop_var>`.

**Example:**

```yaml
input:
  vars:
    iterations: int

workflow:
  steps:
    - code: {lang: python, script: "result = 3", def: iterations}
    - for: i in range({{iterations}})
      def: iteration_outputs
      steps:
        - code:
            lang: python
            script: "result = f'This is iteration number {i}'"
            def: current_message # Collected into iteration_outputs
```
`iteration_outputs` will be `["This is iteration number 0", "This is iteration number 1", "This is iteration number 2"]`.

### 3. While Loop (Conditional Iteration)

Executes a block of steps as long as a specified condition evaluates to `True`.

**Syntax:**

Can be defined using either `while:` or `loop:` as the main key if the expression is a condition.

```yaml
- while: {{<condition_expression>}}
  def: <output_list_var> # Optional
  steps:
    - ... # Steps to execute while condition is true
    - ...

# Alternatively, using the 'loop:' key for a while loop:
- loop: {{<condition_expression>}} # Treated as a while loop
  def: <output_list_var> # Optional
  steps:
    - ...
```

*   `{{<condition_expression>}}`: A template expression that must evaluate to a boolean (`True` or `False`). The loop continues as long as this expression is `True` *before* each iteration's `steps` are executed.
*   **Context Scoping**: Unlike `for` loops, the `while` loop's `steps` operate on the *same context* as the `while` loop itself (which is typically the parent workflow's context or the context of an enclosing step). This means changes made to context variables within the `steps` of a `while` loop **will persist** across iterations and can affect the loop's own condition or subsequent steps after the loop. It is crucial that the `steps` within a `while` loop eventually modify variables in a way that causes the `<condition_expression>` to become `False`, otherwise an infinite loop will occur (though the interpreter has a safety break after a very high number of iterations).

**Example:**

```yaml
workflow:
  steps:
    - code: {lang: python, script: "result = 0", def: counter}
    - code: {lang: python, script: "result = []", def: collected_values} # Initialize list to append to

    - while: "{{counter}} < 3"
      def: loop_step_results # Will collect the output of the last step (the updated counter)
      steps:
        - code:
            lang: python
            script: "collected_values.append(counter); result = collected_values"
            # No 'def' here, modifying 'collected_values' in place
        - code:
            lang: python
            script: "result = counter + 1"
            def: counter # Update counter, this is also the value collected by loop_step_results
```
In this example:
*   `collected_values` (modified in-place) will become `[0, 1, 2]`.
*   `loop_step_results` will become `[1, 2, 3]` (the value of `counter` at the end of each iteration where it was defined).
*   After the loop, `counter` in the main context will be `3`.

## Output Collection (`def` key)

*   If the `LoopStep` has a `def: <variable_name>` attribute, a list is created.
*   In each iteration of the loop, the output of the *very last step executed within that iteration's `steps` block* is appended to this list.
*   If the last step in an iteration does not produce an output (e.g., an `IfStep` where the taken branch has no `def` on its final step, or a `CodeStep` that doesn't set `result`), `None` might be appended for that iteration, or the behavior might depend on the specific step. It's best practice for the last step within a collecting loop iteration to consistently produce a value if defined output is desired.
*   If the loop does not execute at all (e.g., empty collection for `for-each`, or an initially false condition for `while`), the defined variable will be an empty list `[]`.

## Important Considerations

*   **Infinite Loops**: For `while` loops, ensure the loop condition will eventually become `False` through actions within the loop's `steps`. The interpreter has a maximum iteration count (currently 1000) as a safety measure to prevent true infinite hangs.
*   **Context Modification in `while` loops**: Be mindful that `while` loops modify the shared context. This is powerful but requires care.
*   **Performance**: Loops iterating many times, especially if each iteration involves LLM calls or complex tool executions, can be slow and costly. Design workflows efficiently.
```
