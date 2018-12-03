import json

ASSEMBLER_CONST = 1.25

with open("recipes.json") as f:
    all_recipes = json.load(f)


def get_recipe_by_name(name):
    for recipe in all_recipes:
        if recipe["name"] == name:
            return recipe

    raise KeyError(name)

def reduce_products(recipe_name:str, ips:float, indent=0):
    recipe = get_recipe_by_name(recipe_name)


    single_machine_ips = (recipe["produce-qty"] * ASSEMBLER_CONST) / recipe["time"]
    required_makers = ips / single_machine_ips

    print(indent*" - ", "You need", required_makers, "machines making", recipe_name, "to reach", ips, recipe_name + "/s")

    for name, qty in map(lambda x: x.values(), recipe["items"]):

        if name in {"iron-plate", "copper-plate", "coal", "Petroleum gas", "Water", "Heavy oil", "Stone", "Solid fuel"}:
            continue

        reduce_products(name, ips*qty, indent+1)




reduce_products("launched-rocket", 1/300)