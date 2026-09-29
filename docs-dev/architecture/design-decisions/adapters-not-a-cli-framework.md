# Adapters instead of an own CLI framework

Users keep argparse/click/cyclopts; confarg also parses argv itself, so no CLI library is
needed. Help for large, dynamic configurations is inevitably long and incomplete (derived
classes' fields are unknown until selected), and configuration files are the primary
interface, so a rich CLI UX is a secondary goal.
