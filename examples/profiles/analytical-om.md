# Dynamic Allocation with Strategic Service Providers

## Research question

How should a platform dynamically allocate demand when providers can invest in
service quality and manipulate the signals used for learning?

## Framework and primitives

A finite-horizon platform routes stochastic demand between two providers. Each
provider privately chooses costly quality effort before customers generate
noisy ratings. The platform observes rating histories, updates beliefs, and
chooses allocations and commissions. State variables are posterior quality
beliefs and remaining horizon.

## Central mechanism

Exploration creates information but also changes provider effort incentives.
The platform may deliberately diversify allocations to preserve both learning
and discipline.

## Method

Dynamic analytical model solved by backward induction, with equilibrium effort
and numerical comparative statics.

## Key assumptions

Signals satisfy monotone likelihood ratio; effort has convex cost; providers
cannot directly observe the competitor's effort.

## Contribution delta

Unlike standard bandit allocation, information is endogenous to strategic
provider effort. Unlike static moral-hazard models, allocation changes the
future value of information.

## Closest papers

List the two or three papers that share both dynamic learning and endogenous
provider behavior, explaining the missing primitive or mechanism in each.

## Watch

- Keywords: strategic bandits, endogenous information, platform allocation
- Authors:
- Venues or working-paper series: Management Science, Operations Research, M&SOM

## Exclude

Pure prediction papers with no platform decision or strategic provider action.

## Triage preferences

Read now if a paper changes the equilibrium learning-effort mechanism; watch
application evidence that can calibrate signal quality or effort cost.
