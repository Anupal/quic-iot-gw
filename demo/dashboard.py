from nicegui import ui
import json
import plotly.graph_objects as go
import networkx as nx
import os

# Generate sample sensor data for 20 devices with geographic locations (latitude and longitude for Dublin)
sensor_data = {}
protocols = ['MQTT', 'CoAP']
types = ['Temperature', 'Humidity', 'Pressure']

# Function to create and update the table
def create_table():
    columns = [
        {'name': 'id', 'label': 'ID', 'field': 'id', 'required': True, 'align': 'left'},
        {'name': 'type', 'label': 'Type', 'field': 'type', 'required': True, 'align': 'left'},
        {'name': 'protocol', 'label': 'Protocol', 'field': 'protocol', 'required': True, 'align': 'left'},
        {'name': 'health', 'label': 'Health', 'field': 'health', 'required': True, 'align': 'left'},
        {'name': 'reading', 'label': 'Reading', 'field': 'reading', 'required': True, 'align': 'left'},
    ]

    table = ui.table(columns=columns, rows=[], title='Sensor Data').classes('w-full')

    def update_table():
        rows = [
            {'id': sensor_id, **values}
            for sensor_id, values in sensor_data.items()
        ]
        rows.sort(key=lambda x: int(x['id']))
        table.rows = rows
        ui.update(table)

    ui.timer(5, update_table)


# Function to create the static network graph
def create_network_graph():
    graph = ui.plotly({}).classes('w-full h-[400px]')

    def generate_graph():
        G = nx.Graph()

        # Add nodes for each protocol with specific colors
        protocol_colors = {
            'MQTT': 'blue',
            'CoAP': 'yellow',
        }

        protocols = set(sensor['protocol'] for sensor in sensor_data.values())
        for protocol in protocols:
            G.add_node(protocol, color=protocol_colors[protocol])

        # Add nodes for each sensor and connect to its protocol
        for sensor_id, sensor in sensor_data.items():
            G.add_node(f"Sensor {sensor_id}", color='black')  # Sensors are black
            G.add_edge(f"Sensor {sensor_id}", sensor['protocol'])

        # Generate positions for nodes
        pos = nx.spring_layout(G)

        # Create edge trace
        edge_x = []
        edge_y = []
        for edge in G.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=0.5, color='#888'),
            hoverinfo='none',
            mode='lines')

        # Create node trace
        node_x = []
        node_y = []
        node_color = []
        for node in G.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)
            node_color.append(G.nodes[node]['color'])

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode='markers',
            hoverinfo='text',
            marker=dict(
                showscale=False,
                size=10,
                color=node_color,
                line_width=2))

        # Set the hover text for nodes
        node_text = []
        for node in G.nodes():
            if node in protocol_colors:
                node_text.append(f'{node} (Protocol)')
            else:
                sensor_id = node.split()[1]
                sensor = sensor_data[sensor_id]
                node_text.append(f'Sensor {sensor_id}<br>Type: {sensor["type"]}')

        node_trace.text = node_text

        # Create the figure
        fig = go.Figure(data=[edge_trace, node_trace],
                        layout=go.Layout(
                            title='Network graph',
                            titlefont_size=16,
                            showlegend=False,
                            hovermode='closest',
                            margin=dict(b=20, l=5, r=5, t=40),
                            annotations=[dict(
                                text="",
                                showarrow=False,
                                xref="paper", yref="paper",
                                x=0.005, y=-0.002)],
                            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                        )

        return fig

    def update_graph():
        if sensor_data:
            graph.update_figure(generate_graph())

    update_graph()  # Initial map creation
    ui.timer(3, update_graph)


# Function to create and update the map with sensor locations
def create_map():
    map_plot = ui.plotly({}).classes('w-full h-[400px]')

    def generate_map():
        latitudes = [sensor['lat'] for sensor in sensor_data.values()]
        longitudes = [sensor['lon'] for sensor in sensor_data.values()]
        readings = [sensor['reading'] for sensor in sensor_data.values()]
        healths = [sensor['health'] for sensor in sensor_data.values()]
        texts = [
            f"ID: {sensor_id}<br>Type: {sensor['type']}<br>Reading: {sensor['reading']}<br>Health: {sensor['health']}"
            for sensor_id, sensor in sensor_data.items()]

        fig = go.Figure(go.Scattermapbox(
            lat=latitudes,
            lon=longitudes,
            mode='markers',
            marker=go.scattermapbox.Marker(
                size=14,
                color=['green' if health == 'Good' else 'orange' if health == 'Fair' else 'red' for health in healths],
                opacity=0.7
            ),
            text=texts,
            hoverinfo='text'
        ))

        fig.update_layout(
            mapbox_style="open-street-map",
            mapbox_center_lat=53.34403687091694,
            mapbox_center_lon=-6.255869791096676,
            mapbox_zoom=14,
            margin={"r": 0, "t": 0, "l": 0, "b": 0}
        )

        return fig

    def update_map():
        map_plot.update_figure(generate_map())

    update_map()  # Initial map creation
    ui.timer(3, update_map)


# Task to update sensor values periodically
def update_sensor_values():
    if os.path.exists("sensor_data_coap.json"):
        with open("sensor_data_coap.json") as file:
            data = file.read()
            data = json.loads(data)

        for sensor_id in data:
            sensor_data[sensor_id] = data[sensor_id]

    if os.path.exists("sensor_data_mqtt.json"):
        with open("sensor_data_mqtt.json") as file:
            data = file.read()
            data = json.loads(data)

        for sensor_id in data:
            sensor_data[sensor_id] = data[sensor_id]


@ui.page('/')
def home():
    ui.label('Sensor Data Dashboard').classes('text-h3 w-full')
    with ui.column().classes('w-full'):
        create_table()
        # ui.label('Network Graph').classes('text-h5 w-full')
        # create_network_graph()
        ui.label('Sensor Locations in Dublin').classes('text-h5 w-full')
        create_map()
    ui.timer(3, update_sensor_values)


ui.run(host="0.0.0.0", port=8080)
