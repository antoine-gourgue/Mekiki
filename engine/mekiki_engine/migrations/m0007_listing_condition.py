# The condition of a Japanese listing ("new", "like_new"…), when its marketplace gives it.
SQL = """
ALTER TABLE listings ADD COLUMN condition TEXT;
ALTER TABLE favorites ADD COLUMN condition TEXT
"""
