# Robust Routing under Distribution Shift

## Research question

How should a real-time routing policy adapt when demand and travel-time
distributions shift across neighborhoods?

## Framework and primitives

A dispatcher assigns jobs to a fleet on a spatial network. Inputs are arrival
streams, travel-time distributions, vehicle states, and service constraints;
outputs are assignments, delays, and geographic service disparities.

## Central mechanism

Policies trained on average historical demand can amplify local service gaps
when uncertainty is spatially uneven. Robustness must protect both system
performance and tail neighborhoods.

## Method

Distributionally robust optimization with an offline simulation benchmark and
out-of-distribution evaluation.

## Key assumptions

The ambiguity set is estimated from finite samples; travel-time shocks are
partially correlated across adjacent zones; feasibility is enforced online.

## Contribution delta

The project couples spatially structured ambiguity with a service-equity
constraint, rather than adding an ex post fairness metric to a nominal policy.

## Closest papers

List robust dynamic routing and geographic fairness papers, distinguishing
model primitives, ambiguity sets, and operational constraints.

## Watch

- Keywords: distributionally robust routing, spatial demand shift, service equity
- Authors:
- Venues or working-paper series: Transportation Science, INFORMS Journal on Computing

## Exclude

Static map visualization and generic domain-adaptation papers without a routing
decision or operational constraint.

## Triage preferences

Read now for a stronger ambiguity construction, tractable policy class, or
theoretical conflict with the equity constraint; watch new benchmark datasets.
