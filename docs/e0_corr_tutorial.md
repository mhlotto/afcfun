# Football Correlation Analysis Tutorial (E0 Dataset)

This tutorial explains how to use e0_corr.py to explore correlations between football match statistics and performance outcomes.
It focuses on what questions you are asking and how the tool answers them.

---

## 1. What this tool is for

At a high level, this codebase answers questions like:

- Which match statistics are associated with winning?
- Are some stats more related to dominance than raw results?
- Which correlations still look real after accounting for multiple testing?

This is exploratory analysis, not causal inference.

---

## 2. The data model (important)

Each match is normalized into a team-centric row:

- Team stats (shots, corners, fouls, etc.)
- Opponent stats (opponent_shots, opponent_corners, etc.)
- Match outcome information

This allows you to treat each match as:

"How did this team perform relative to its opponent?"

---

## 3. Choosing the target (what you correlate against)

The target defines what performance means.

### Available targets

| Target | Meaning |
|------|--------|
| outcome | Win=1, Draw=0, Loss=-1 |
| points | Win=3, Draw=1, Loss=0 |
| goal_diff | Goals for minus goals against |
| goals_for | Team goals scored |
| goals_against | Goals conceded |
| winloss | Win=1, Draw or Loss=0 |

### Guidance

- Use goal_diff for overall performance quality.
- Use points when thinking in league terms.
- Use winloss only when you explicitly want binary outcomes.

### Further reading
- https://en.wikipedia.org/wiki/Goal_difference
- https://en.wikipedia.org/wiki/Dependent_and_independent_variables

---

## 4. Choosing features (what explains the target)

Football is relative. Raw counts are often misleading.

### Feature sets

| Feature set | Includes |
|-----------|---------|
| base | Team stats only |
| with_opponent | Team and opponent stats |
| with_diffs | Team and (team minus opponent) differences |
| all | Team, opponent, and differences |

### Why differences matter

Example:
- 10 shots vs opponent 3 shots means dominance
- 10 shots vs opponent 15 shots means pressure

The difference captures this directly.

### Further reading
- https://en.wikipedia.org/wiki/Feature_engineering
- https://statsbomb.com/articles/soccer/what-are-shots-worth/

---

## 5. Choosing the correlation method

Correlation answers how strongly two variables are associated.

### Methods

| Method | Use case |
|------|---------|
| pearson | Linear relationships |
| spearman | Rank based, robust |
| kendall | Conservative rank based |
| pointbiserial | Binary target only |
| distance | Any dependence, including nonlinear |

### Guidance

- Default: spearman
- Use pearson only if you expect linearity.
- Use distance sparingly for small samples.

### Further reading
- https://en.wikipedia.org/wiki/Correlation
- https://en.wikipedia.org/wiki/Spearman%27s_rank_correlation_coefficient
- https://en.wikipedia.org/wiki/Distance_correlation

---

## 6. P-values and uncertainty

A correlation coefficient alone is misleading without uncertainty.

- P-value: how surprising this correlation is under a null hypothesis
- Confidence interval: plausible range of true correlation values

### Methods

- Analytic (fast, assumption heavy)
- Permutation (robust, slower)
- Bootstrap (distribution free CI)

### Further reading
- https://en.wikipedia.org/wiki/P-value
- https://en.wikipedia.org/wiki/Bootstrap_(statistics)

---

## 7. Multiple comparisons (critical)

If you test many stats, some will appear significant by chance.

### The problem

Testing 40 features at alpha=0.05 means about 2 false positives on average.

### The solution: FDR (Benjamini Hochberg)

- Controls the false discovery rate
- Less strict than Bonferroni
- Appropriate for exploratory analysis

Enable with:
--adjust bh
or
--fdr

Filtering then uses q-values, not raw p-values.

### Further reading
- https://en.wikipedia.org/wiki/Multiple_comparisons_problem
- https://en.wikipedia.org/wiki/False_discovery_rate
- https://en.wikipedia.org/wiki/Benjamini%E2%80%93Hochberg_procedure

---

## 8. A recommended starting workflow

```
python3 e0_corr.py \
  --team Arsenal \
  --target goal_diff \
  --feature-set with_diffs \
  --method spearman \
  --fdr \
  --filter-significant
```

This asks:

"Which relative match stats are associated with goal dominance, after accounting for multiple testing?"

---

## 9. Interpreting results (what not to conclude)

A significant correlation does not mean:
- The stat causes wins
- The stat should be maximized
- The stat will generalize across leagues or eras

Always sanity check:
- Home vs away splits
- Stability across seasons
- Sample size (n)

### Further reading
- https://en.wikipedia.org/wiki/Correlation_does_not_imply_causation

---

## 10. Where to go next

Natural extensions:
- Logistic regression for win probability
- Partial correlations controlling for goals
- Rolling window analysis
- Cross team comparisons

This tool gives you signals. Judgment is still required.

---

End of tutorial.
