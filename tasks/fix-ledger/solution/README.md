# ledger

A tiny package that parses money strings into integer cents and summarises
spending by category.

## Usage

```python
from ledger import net, over_budget, summarize, to_cents

to_cents("-$12.50")                                   # -1250
summarize([("food", "10.00"), ("food", "5.00")])      # {'food': 1500}
net([("pay", "100"), ("rent", "(40.00)")])            # 6000
over_budget([("food", "15.00")], {"food": 1400})      # ['food']
```
