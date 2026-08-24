# MACI

MACI is a project designed to analyze and evaluate collaboration between multiple AI agents in a shared environment.

---

## Project Overview

Most existing multi-agent evaluation methods focus mainly on whether the agents successfully complete a task or how much reward they receive.

However, a final success or failure score alone cannot explain what actually happened during the collaboration process.

For example, a failure may occur because:

* One agent provided incorrect information
* Another agent misunderstood a message
* The agents failed to coordinate their roles
* An agent made an incorrect plan
* An agent failed to detect or recover from an earlier mistake

MACI aims to identify these differences by analyzing the full interaction process between agents.

---

## Core Objective

The main research question of MACI is:

> Which agent caused the failure, at what point did the failure become decisive, and which message or action had the greatest influence?

MACI records the complete interaction trace of each episode, including:

* Agent observations
* Messages exchanged between agents
* Selected actions
* Changes in the environment
* Task progress
* Rewards and milestones

This allows the system to analyze not only the final result, but also the process that led to it.

---

## Failure Analysis

When a collaboration failure occurs, MACI attempts to identify:

* The agent responsible for the failure
* The decisive interaction step
* The message or action that influenced the outcome
* Whether the failure could have been detected or recovered from

Failures may be classified into categories such as:

* Perception
* Belief Tracking
* Communication
* Planning
* Coordination
* Execution
* Verification
* Evaluation

---

## Counterfactual Replay

MACI uses counterfactual replay to verify whether a specific message or action actually caused a failure.

The system can replay the same situation after changing one part of the original interaction, such as:

* Removing a message
* Correcting incorrect information
* Replacing an agent's action
* Changing the order of messages
* Delaying or blocking communication
* Swapping agent roles

The results of the original execution and the modified execution are then compared.

This makes it possible to explain failures using reproducible evidence rather than relying only on assumptions or generated explanations.

---

## Project Goal

The final goal of MACI is to build an evaluation framework that can measure and explain multi-agent collaboration.

Rather than asking only:

> Did the agents succeed?

MACI focuses on a more detailed question:

> How did the agents collaborate, where did the collaboration fail, and why did that failure occur?

---

## Repository Access

The following members are authorized to access and modify this repository:

* Jihoon Park
* Yeomyeong Lee
* Henry Kim
* Hanwook Choi
