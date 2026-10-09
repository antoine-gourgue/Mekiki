# Sellers blocked for a "refusal" that accepted proxies and refused something else
# ("代行OK、値下げ不可"): they are unblocked, and checked again with the narrower rule.
SQL = """
DELETE FROM blocked_sellers
WHERE reason LIKE 'refuse les achats par un intermédiaire%'
  AND (reason LIKE '%ok%' OR reason LIKE '%歓迎%' OR reason LIKE '%大丈夫%'
       OR reason LIKE '%可能%' OR reason LIKE '%«%、%»%' OR reason LIKE '%«%,%»%')
"""
