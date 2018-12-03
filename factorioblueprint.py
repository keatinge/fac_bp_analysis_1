import json
import zlib
import enum
import base64
import functools
import itertools
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


recipes = json.loads(open("recipes.json").read())
def get_recipe_by_name(name):
    for rec in recipes:
        if rec["name"] == name:
            return rec
    raise NameError("Couldn't find recipe with name {}".format(name))


class Directions(enum.Enum):
    UP = 0
    RIGHT = 2
    DOWN = 4
    LEFT = 6


class Inserter(object):
    def __init__(self, entity_dict):
        self.x = entity_dict["position"]["x"]
        self.y = -entity_dict["position"]["y"]
        # For some reason Factorio developers don't include the direction in the data if it is up
        self.direc = Directions(entity_dict.get("direction", 0))
        self.reach = 2 if "long" in entity_dict["name"] else 1
        self.name = entity_dict["name"]
        self.width = 1
        self.height = 1
        self.throughput = self.get_max_insertion_speed()
        self.distance_vectors = {
            Directions.UP: (0, -self.reach),
            Directions.LEFT: (self.reach, 0),
            Directions.DOWN: (0, self.reach),
            Directions.RIGHT: (-self.reach, 0)
        }
        self.computed_tp = None


    def get_max_insertion_speed(self):
        # TODO: Belt speed and burner?
        throughputs = {
            "inserter": .74,
            "long-handed-inserter": 1.11,
            "fast-inserter": 2.22,
            "filter-inserter": 2.22,
            "stack-inserter": 3.81,
            "stack-filter-inserter": 3.81
        }
        return throughputs[self.name]+2 #TODO TODO TODO !!!!!!!!!!!! TODO !!!!!!!!!!!!!!!!!!

    def get_output_delta_vector(self):
        return self.distance_vectors[self.direc]


    def get_input_delta_vector(self):
        reverse_direction = lambda x: Directions((((x.value / 2) + 2) % 4) * 2)  # I promise this works
        return self.distance_vectors[reverse_direction(self.direc)]


    def get_output_position(self):
        vec = self.get_output_delta_vector()
        return vec[0] + self.x, vec[1] + self.y


    def get_input_position(self):
        vec = self.get_input_delta_vector()
        return vec[0] + self.x, vec[1] + self.y




    #Assemblers trust the inserters throughput, but the inserters have to request throughput from their assemblers
    def calculate_throughput(self, bp):

        if self.computed_tp is not None: return self.computed_tp

        # Figure out what this inserter is taking from, if it's an assembler, its either that assemblers throughput
        # Or this inserters hand-moving speed

        input_obj = bp.get_output_at_position(*self.get_input_position())


        if input_obj is None:
            ret = {"name" : "__anything__", "items-per-second" : self.get_max_insertion_speed()}

        else:
            #Taking from assembler

            input_tp = input_obj.request_inserter_throughput(bp, self.get_max_insertion_speed())

            ret = {**input_tp, **{"items-per-second" : min([input_tp["items-per-second"], self.get_max_insertion_speed()])}}

        self.computed_tp = ret
        return ret



        #return {"name" : "copper-plate", "items-per-second" : 100}


class Assembler(object):
    def __init__(self, entity_dict):
        self.x = entity_dict["position"]["x"]
        self.y = -entity_dict["position"]["y"] #Dont ask
        self.name = entity_dict["name"]
        self.width = 3
        self.height = 3
        self.recipe = entity_dict["recipe"]
        self.computed_tp = None
        self.remaining_tp = None

    def input_contains(self, x, y):
        assembler_x_rng = list(range(self.x - 1, self.x + 2))
        assembler_y_rng = list(range(self.y - 1, self.y + 2))

        return x in assembler_x_rng and y in assembler_y_rng


    def output_contains(self, *args, **kwargs):
        # The input and output on an assembler are identical
        return self.input_contains(*args, **kwargs)


    def request_inserter_throughput(self, bp, max_inserter_throughput):
        if not self.computed_tp: self.calculate_throughput(bp)

        print(self.remaining_tp)
        throughput = min([max_inserter_throughput, self.remaining_tp])



        self.remaining_tp -= throughput


        return {"name" : self.recipe, "items-per-second" : throughput}








    def calculate_throughput(self, bp):
        if self.computed_tp is not None: return self.computed_tp
        inserters_in = bp.get_inserters_into(self)

        recipe_data = get_recipe_by_name(self.recipe)
        inserters_throughput = [ins.calculate_throughput(bp) for ins in inserters_in]

        #If the the inserters are moving the material fast enough, our throughput is crafting time
        #If they dont move the material fast enough then the throughput is 1 item everytime you get the materials to make that item

        required_anything = 0 # How much stuff needs to be pulled in by inserters carrying *anything*


        times = [recipe_data["time"]]
        for item in recipe_data["items"]:
            actual_tp = sum(itp["items-per-second"] for itp in inserters_throughput if itp["name"] == item["name"])

            if self.recipe == "electronic-circuit":
                print("abc", item["name"], actual_tp)
            if actual_tp == 0:
                required_anything += item["qty"]
            else:
                times.append(item["qty"] / actual_tp)

        if required_anything:

            anythings_per_second = sum(itp["items-per-second"] for itp in inserters_throughput if itp["name"] == "__anything__")

            assert anythings_per_second > 0, f"Anythings are needed for {self.recipe} but there is 0 aps"
            anything_time = required_anything/anythings_per_second
            times.append(anything_time)






        tp_result = {"name": self.recipe, "items-per-second" : recipe_data["produce-qty"] / max(times)}

        self.computed_tp = tp_result
        self.remaining_tp = self.computed_tp["items-per-second"]
        return tp_result



    def __repr__(self):
        return f"<{self.name} ({self.x}, {self.y}) {self.recipe}>"



class Blueprint(object):
    def __init__(self, bp_str):
        bp_dict = json.loads(zlib.decompress(base64.b64decode(bp_str[1:])).decode("utf-8"))

        #print(json.dumps(bp_dict, indent=2))
        self.raw_entities = bp_dict["blueprint"]["entities"]
        self.inserters = []
        self.assemblers = []
        self.parse_entities()

    def parse_entities(self):
        print("Beginning parsing", len(self.raw_entities), "raw entities.")

        for entity in self.raw_entities:
            if "inserter" in entity["name"]:
                self.inserters.append(Inserter(entity))
            elif "assembling" in entity["name"] and "recipe" in entity:
                self.assemblers.append(Assembler(entity))

        print("Parsed", len(self.inserters), "inserters and", len(self.assemblers), "assemblers")

    def get_inserters_into(self, obj):

        ins = []
        for inserter in self.inserters:
            if obj.input_contains(*inserter.get_output_position()):
                ins.append(inserter)

        return ins


    def get_output_at_position(self, x, y):
        # TODO: Add more outputs, belts
        for assem in self.assemblers:
            if assem.output_contains(x, y):
                return assem

        return None



    def analyze(self):

        ret = {}
        tps = [] #Throughputs
        for assembler in self.assemblers:
            tp = assembler.calculate_throughput(self)
            tps.append(tp)

        get_name = lambda x: x["name"]


        for key, outputs in itertools.groupby(sorted(tps, key=get_name), get_name):
            ips = sum([o["items-per-second"] for o in outputs])
            ret[key] = ips
        return ret



    def vizualize(self):
        matplotlib.rc("font", size=5)
        axes = plt.gca()
        axes.set_xlim([-20, 20])
        axes.set_ylim([-20, 20])


        ins_xs = []
        ins_ys = []
        for inserter in self.inserters:
            ins_xs.append(inserter.x + .5)
            ins_ys.append(inserter.y + .5)
            #plt.annotate(inserter.name, xy=(inserter.x + .5, inserter.y + .5))
            plt.arrow(inserter.x + 1, inserter.y + .5, *inserter.get_output_delta_vector(), head_width=.1)
            plt.annotate(f'{round(inserter.calculate_throughput(self)["items-per-second"], 3)}', xy=(inserter.x + .5, inserter.y - .2))
            axes.add_patch(Rectangle((inserter.x, inserter.y), 1, 1, alpha=.3, color="blue"))


        ass_xs = []
        ass_ys = []
        for assembler in self.assemblers:
            ass_xs.append(assembler.x + .5)
            ass_ys.append(assembler.y + .5)
            plt.annotate(f'{round(assembler.computed_tp["items-per-second"], 3)} {assembler.recipe}/s', xy=(assembler.x, assembler.y-.5))
            axes.add_patch(Rectangle((assembler.x-1, assembler.y-1), 3, 3, alpha=.3, color="orange"))


        plt.scatter(ins_xs, ins_ys, color="blue")
        plt.scatter(ass_xs, ass_ys, color="orange")
        plt.show()






fucked2 = "0eNqdk9FuhCAQRf9lniER17pdf6XZNMhOt5PIaACbGuO/F7VpN1nTlT6RYeDcyw0zQt302DniANUIZFr2UL2M4OnKupn3wtAhVEABLQhgbedKe4+2boiv0mrzTozyAJMA4gt+QqWmswDkQIFw5S3F8Mq9rdHFAz+kN+2DJPboQmwI6Fofb7U8S0eSLAQMcckj/EIOzdorJ3HHzP92d4/Of9ERTMszTdt16KTRdYOwIXLYazzb7btI9P1tW93axiYquJbJSEPO9BS2zD/9LyGVElCZGJB6HNAxDZk9Jj4nfr8dJk97kfkWsZgHZhmx6mYiBXyg86tkUeRlpspjeZqmLwpRPKc="


mil_sci = "0eNqdm+9umzAUxd/Fn0HCf7BxXmWqJpJYrTUgEdBpUZV3H2m3LlppOed+bNr8sH3P4V7bty9q3z2n85iHWe1eVD6chkntvr2oKT8ObXf7bL6ck9qpPKdeFWpo+9tP89gO0/k0zuU+dbO6FioPx/RL7fS12PxyO02p33d5eCz79vCUh1SaO4S5PhQqDXOec3obzOsPl+/Dc79P4/KMz4ZRqPNpWr52Gm7PXlC2UBe1K7Vf6Mc8psPb79xtkP9BDQw1ONTC0NL9obptqnun5mFK47x89pFn13lmhVd/HZmPbH3HXsj5NcZ97vLcjpdyOuQ0HFJ5bg8/1Mrj/PvjutPyoKd2Cfux/Hwqf59Wb88kACuj8YVpaKEB0Ys0tN6G6oqWLzBUrWkqMtZ/VuvTMT/3ZeqWvx/zoTyfuvSFlu11DScwmQFG6XisBbBis2mR2bTUbWbbHjqQgdRfxpF3GxLGSEsYoJqKHiugDcPbDaEaXsgVgBXYTgNYKrnpbZGamsgJCM/TQUJWM9CCQqi8pZAQ8ZYCqLai9dQAVE1TI0A1hEibbU1ZK0wKjSgnWCfLCRGYCeE2ZGE8K2BEE4HVLwJtWCiiM7pWBKCuEpZfYS1rO95gwL7J8TkrAFSpzWqRzZzQZn7bF66WVV7rIaRNhkSQNhkCpU2GqII2GQCt+WwG7Mdq3mzAfqxmshmwCa8tngMQnGPjg6xkzSoJgdKlIRIdujJEoA0tJGBXVEeaCuxffEXIE9i1ei3MAkZ22mVkWcACMyGMhiyMY+ULaMLXrHwRKG00RGe00RBoIz3rWsvUnjYYsEkMfKoCtnNB6DLZKVeQmawCTpSt8IxrLX6BTmXISrMOQzTBGgxh0hUhMnk6kQGvl0DbDBhpQ6Qx4Biq0fC7H6EZUkPIhC3JBCLTsCkKYbKlIDJ3zyoIKC+bwEKBBNU0uCyRG7Moe+3LbhJjJXrtA6VVxO0FrEpk7QUELrL2Qq4mWXshTNZeyNy9rKqq15JypG0FnFREOi8Bu7YoNFeQ3RxWMncBx1e60qKqajV+umLdBd2ns/byCJT1FwRlDQZNn05gDUKlrRYQKpHCAiLOCL/7EZxm74qROWu2BwoJj2Z7oCCoJaHQ9OnmDOS6VOuaxUaE6onKv0IUFYR760qWCO46M5hEEJGp4F6DloZuzEACaFizQWIzrNswKms3aAGcrN7Sq6cg2tA2gzp9DJ2zkL4EbaRuszK3GZnboIatu9YNpu76JI6WNRsURku7DYmipd0GjZV1GzZWPrshzZyWtx3S0GiZ9AZsvbXFu3gxHtsFhU2bvTaGYuTYPl6MyjYWQivAN2l87A5+KN7+N2B3938IhfqZxun1D7xzxlfaBx+v19+3FSVh"


real_circ = "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"

bp = Blueprint(real_circ)
print(bp.analyze())
print("-"*30)
bp.vizualize()
