# ROS 2 Robot Agent for Autonomous Navigation

A modular Robot Agent built with ROS 2, TurtleBot3, Gazebo, and Nav2. The system translates high-level navigation commands into robot actions, handles navigation failures, and evaluates task execution through an automated benchmark.

## System Architecture

```text
Benchmark
    |
    v
Robot Agent
    |
    v
Navigation Skill
    |
    v
Nav2
    |
    v
TurtleBot3 in Gazebo

Results:
Nav2 → Skill → Agent → Benchmark
```

## Key Features

- **Task execution:** Converts commands such as `go to kitchen` into navigation goals.
- **Modular architecture:** Separates task orchestration from low-level navigation.
- **ROS 2 Actions:** Uses asynchronous goal handling, feedback, and final results.
- **Failure handling:** Reports Nav2 navigation errors and supports configurable retry behavior.
- **Task tracking:** Uses unique task IDs to match commands with their results.
- **Automated evaluation:** Runs sequential navigation trials and records results in CSV.

## Benchmark Results

The benchmark included 10 navigation tasks alternating between `kitchen` and `room`, followed by two intentionally blocked navigation tasks.

| Metric | Result |
|---|---|
| Normal navigation success rate | 10/10 (100%) |
| Average normal navigation duration | 14.89 s |
| Blocked scenarios returning error 208 | 2/2 |
| Tasks with final results | 12/12 |

### Experimental Notes

- The navigation tasks were performed sequentially. Each task started from the robot's position after the previous task.
- The `blocked` goal was intentionally used to test failure reporting.
- Error code `208` was observed during the blocked scenarios.
- Agent-level retries were not triggered during this benchmark (`agent_retries = 0`).
- These results describe a small simulation-based test, not a general guarantee of navigation success.

## Technologies

Python, ROS 2, ROS 2 Actions, Nav2, TurtleBot3, Gazebo

## Future Improvements

- Validate Agent-level recovery using controlled failure injection.
- Extend benchmark coverage to additional maps and navigation scenarios.
- Compare navigation performance under different failure conditions.
## How to Run

### 1. Build the Workspace

This project uses ROS 2 Lyrical, Nav2, TurtleBot3, and Gazebo.

Source the ROS 2 and Nav2 environments, then build the Robot Agent workspace:

```bash
source /opt/ros/lyrical/setup.bash
source ~/nav2_ws/install/setup.bash

cd ~/robot_agent_ws
colcon build
source install/setup.bash
```

### 2. Source the Environment

Run the following commands in **each new terminal** before starting a node:

```bash
source /opt/ros/lyrical/setup.bash
source ~/nav2_ws/install/setup.bash
source ~/robot_agent_ws/install/setup.bash
```

### 3. Start TurtleBot3 Simulation and Nav2

**Terminal 1:**

```bash
ros2 launch nav2_bringup tb3_simulation_launch.py \
  params_file:=$HOME/robot_agent_ws/configs/nav2_params_tb3.yaml \
  headless:=False
```

Wait until the simulation and Nav2 navigation servers are ready.

### 4. Start the Navigation Skill

**Terminal 2:**

```bash
ros2 run robot_skills navigate_to_pose
```

This node provides the `/navigate_skill` Action interface and forwards navigation goals to Nav2.

### 5. Start the Robot Agent

**Terminal 3:**

```bash
ros2 run robot_agent agent_node
```

The Agent subscribes to `/agent/command`, executes navigation tasks through the Skill layer, and publishes final task results on `/agent/task_result`.

### 6. Send a Manual Navigation Command

**Terminal 4:**

```bash
ros2 topic pub --once /agent/command \
  std_msgs/msg/String "{data: 'go to kitchen'}"
```

Another example:

```bash
ros2 topic pub --once /agent/command \
  std_msgs/msg/String "{data: 'go to room'}"
```

### 7. Run the Automated Benchmark

Once the Agent is idle, run:

```bash
ros2 run robot_agent benchmark
```

The benchmark sends tasks sequentially, uses unique task IDs to match results, and reports navigation success rates and execution durations.

The evaluated 12-trial sequence is defined in `benchmark.py` as:

```python
targets = ['kitchen', 'room'] * 5 + ['blocked'] * 2
```

### 8. View Benchmark Results

The Agent records completed tasks in:

```text
benchmark_result/agent_runs.csv
```

The saved 12-trial experiment is available at:

```text
benchmark_result/benchmark_12_runs.csv
```

To inspect the experimental data:

```bash
cd ~/robot_agent_ws
cat benchmark_result/benchmark_12_runs.csv
```

**Note:** The `blocked` target is intentionally used to test navigation failure reporting. A failed navigation to this target is expected and is evaluated separately from normal navigation success.
