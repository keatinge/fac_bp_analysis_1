import re
import sys
import bs4
import json
import gevent
import requests
import gevent.monkey
import gevent.lock


gevent.monkey.patch_all()
sem = gevent.lock.Semaphore(10)

def get_all_recipe_pages():
    homepage = "https://wiki.factorio.com"
    soup = bs4.BeautifulSoup(requests.get(homepage).text, "html.parser")
    a_els = soup.select("div.tab div.factorio-icon > a")
    all_pages = [homepage + a["href"] for a in a_els]
    return all_pages


def get_internal_name_and_img_recipe(link):
    sem.acquire()

    print("Starting", link)

    try:
        soup = bs4.BeautifulSoup(requests.get(link).text, "html.parser")
        internal_para = soup.select_one("div.infobox-header div.more-content > p").text
        internal_name = re.search(r"Internal name: ([\w-]*)", internal_para).group(1)

        english_name = soup.select_one("div.infobox-header > div.header-text > div > p").text.strip()
        recipe_squares = soup.select("div.infobox table td:nth-of-type(2) > div.factorio-icon")

        time = float(recipe_squares[0].text)
        produce_qty = int(recipe_squares[-1].text)

        items = []

        for item in recipe_squares[1:-1]:
            name = item.select_one("a")["title"]
            qty = int(item.text)

            item_dict = {"name" : name, "qty" : qty}
            items.append(item_dict)

        recipe = {
            "name" : internal_name,
            "produce-qty" : produce_qty,
            "time" : time,
            "items" : items
        }

        namemap = {
            english_name : internal_name
        }
    except Exception as e:
        print("!!!!!!!! Skipping !!!!!!!!! ", link, file=sys.stderr)
        sem.release()
        return None



    sem.release()


    return namemap, recipe


get_internal_name_and_img_recipe("https://wiki.factorio.com/Stone")

def scrape_all():
    pgs = get_all_recipe_pages()

    recipes = []
    name_lookup = {}

    threads = [gevent.spawn(get_internal_name_and_img_recipe, pg) for pg in pgs]
    gevent.joinall(threads)

    for thread in threads:

        if not thread.value:
            continue

        name_conv, recipe = thread.value
        name_lookup.update(name_conv)
        recipes.append(recipe)


    return name_lookup, recipes




json_file = lambda x: json.loads(open(x).read())

name_lookup = json_file("faclookup.json")
recipes = json_file("facrecipes.json")


for recipe in recipes:
    for item in recipe["items"]:
        try:
            item["name"] = name_lookup[item["name"]]
        except KeyError:
            new_name = item["name"].lower().replace(" ", "-")
            print(item["name"], new_name)

with open("recipes.json", "w") as f:
    f.write(json.dumps(recipes, indent=4))

#name_lookup, recipes = scrape_all()
# get_internal_name_and_img_recipe("https://wiki.factorio.com/Raw_fish")
