import random
from pathlib import Path

import geopandas as gpd
import libpysal
import mesa
import mesa_geo as mg

script_directory = Path(__file__).resolve().parent


def get_largest_connected_components(gdf):
    """Get the largest connected component of a GeoDataFrame."""
    # create spatial weights matrix
    w = libpysal.weights.Queen.from_dataframe(
        gdf, use_index=True, silence_warnings=True
    )
    # get component labels
    gdf["component"] = w.component_labels
    # get the largest component
    largest_component = gdf["component"].value_counts().idxmax()
    # subset the GeoDataFrame
    gdf = gdf[gdf["component"] == largest_component]
    return gdf


class SchellingAgent(mg.GeoAgent):
    """Schelling segregation agent."""

    def __init__(self, model, geometry, crs, agent_type=None):
        """Create a new Schelling agent.

        Args:
            unique_id: Unique identifier for the agent.
            agent_type: Indicator for the agent's type (minority=1, majority=0)
        """
        super().__init__(model, geometry, crs)
        self.atype = agent_type

    def step(self):
        """Advance agent one step."""
        similar = 0
        different = 0
        neighbors = self.model.space.get_neighbors(self)
        if neighbors:
            for neighbor in neighbors:
                if neighbor.atype is None:
                    continue
                elif neighbor.atype == self.atype:
                    similar += 1
                else:
                    different += 1

        # If unhappy, move:
        if similar < different:
            # Select an empty region
            empties = [a for a in self.model.space.agents if a.atype is None]
            # Switch atypes
            new_region = random.choice(empties)
            new_region.atype = self.atype
            self.atype = None
            self.remove()
        else:
            self.model.happy += 1

    def __repr__(self):
        return "Agent " + str(self.unique_id)


class GeoSchelling(mesa.Model):
    """Model class for the Schelling segregation model."""

    def __init__(self, density=0.6, minority_pc=0.2, export_data=False):
        super().__init__()
        self.density = density
        self.minority_pc = minority_pc
        self.export_data = export_data

        self.space = mg.GeoSpace(warn_crs_conversion=False)

        self.happy = 0
        self.datacollector = mesa.DataCollector({"happy": "happy"})

        self.running = True

        # Set up the grid with patches for every NUTS region
        ac = mg.AgentCreator(SchellingAgent, model=self)
        data_path = script_directory / "data/nuts_rg_60M_2013_lvl_2.geojson"
        agents_gdf = gpd.read_file(data_path)
        agents_gdf = get_largest_connected_components(agents_gdf)
        agents = ac.from_GeoDataFrame(agents_gdf)
        self.space.add_agents(agents)

        # Set up agents
        for agent in agents:
            if random.random() < self.density:
                if random.random() < self.minority_pc:
                    agent.atype = 1
                else:
                    agent.atype = 0

    def export_agents_to_file(self) -> None:
        self.space.get_agents_as_GeoDataFrame(agent_cls=SchellingAgent).to_crs(
            "epsg:4326"
        ).to_file("data/schelling_agents.geojson", driver="GeoJSON")

    def step(self):
        """Run one step of the model.

        If All agents are happy, halt the model.
        """
        self.happy = 0  # Reset counter of happy agents
        self.agents.shuffle_do("step")
        self.datacollector.collect(self)

        if self.happy == len(self.agents):
            self.running = False

        if not self.running and self.export_data:
            self.export_agents_to_file()
