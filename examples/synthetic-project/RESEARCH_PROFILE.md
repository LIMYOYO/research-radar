# Marketplace Learning Under Strategic Reviews

## Research question

How should a platform jointly choose recommendations and prices when sellers strategically influence noisy consumer reviews?

## Framework and primitives

A two-sided platform observes reviews, updates product-quality beliefs, recommends one of two sellers, and charges a commission. Sellers choose costly review-influence effort before the platform acts.

## Central mechanism

Recommendation affects both current matching value and the future informativeness of reviews. Strategic review effort distorts that exploration-versus-exploitation tradeoff.

## Method

Finite-horizon analytical model with Bayesian learning and Markov-perfect equilibrium, supported by numerical comparative statics.

## Key assumptions

Review signals satisfy monotone likelihood ratio. Seller effort raises favorable-review probability at convex cost. The benchmark removes strategic effort.

## Contribution delta

The project adds endogenous seller manipulation to joint recommendation-and-pricing models and identifies when the platform deliberately diversifies recommendations to discipline manipulation.

## Closest papers

Cao (2026) is closest on joint recommendation and pricing under learning. Luca and Zervas (2016) motivates strategic review manipulation but does not model platform control.

## Watch

- Keywords: platform learning, recommender systems, dynamic pricing, fake reviews
- Authors: Junyu Cao, Michael Luca
- Venues: Management Science, Manufacturing & Service Operations Management

## Exclude

Pure sentiment-classification papers without platform decisions; static review helpfulness prediction.

## Triage preferences

Read now when a paper changes the dynamic mechanism, equilibrium review effort, or the novelty claim. Watch descriptive evidence unless it directly calibrates primitives.
