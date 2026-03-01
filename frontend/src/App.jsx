import React, { useMemo, useState } from "react";
import { APP_CONFIG } from "./constants/appConfig.js";
import defaultLocations from "./constants/defaultLocations.js";
import { PAGES } from "./constants/pageConfig.js";
import HomePage from "./pages/HomePage.jsx";
import SamplePage from "./pages/SamplePage.jsx";
import AgentPage from "./pages/AgentPage.jsx";
import useWorkflowActions from "./hooks/useWorkflowActions.js";
import "./styles.css";

export default function App() {
	const [activePage, setActivePage] = useState(PAGES.HOME);
	const [locations, setLocations] = useState(defaultLocations);
	const [inbound, setInbound] = useState(APP_CONFIG.defaultInbound);
	const [forecasts, setForecasts] = useState([]);
	const [plan, setPlan] = useState(null);

	const productId = APP_CONFIG.productId;

	const {
		sampleLoading,
		sampleMessage,
		forecastLoading,
		forecastMessage,
		agentLoading,
		agentMessage,
		runNotebookForecast,
		runSampleAllocation,
		runAgentPipeline,
	} = useWorkflowActions({
		productId,
		inbound,
		locations,
		setLocations,
		setForecasts,
		setPlan,
	});

	const summary = useMemo(() => {
		const demand = locations.reduce((acc, location) => acc + Number(location.demand_forecast || 0), 0);
		const onHand = locations.reduce((acc, location) => acc + Number(location.inventory_level || 0), 0);
		return { demand, onHand };
	}, [locations]);

	const updateLocation = (locationId, field, value) => {
		setLocations((prev) =>
			prev.map((location) =>
				location.location_id === locationId ? { ...location, [field]: value } : location
			)
		);
	};

	if (activePage === PAGES.HOME) {
		return (
			<HomePage
				summary={summary}
				inbound={inbound}
				onNavigate={(page) => setActivePage(page)}
			/>
		);
	}

	if (activePage === PAGES.SAMPLE) {
		return (
			<SamplePage
				summary={summary}
				inbound={inbound}
				productId={productId}
				locations={locations}
				setInbound={setInbound}
				updateLocation={updateLocation}
				onBack={() => setActivePage(PAGES.HOME)}
				runSampleAllocation={runSampleAllocation}
				sampleLoading={sampleLoading}
				sampleMessage={sampleMessage}
				runNotebookForecast={runNotebookForecast}
				forecastLoading={forecastLoading}
				forecastMessage={forecastMessage}
				forecasts={forecasts}
				plan={plan}
			/>
		);
	}

	return (
		<AgentPage
			summary={summary}
			inbound={inbound}
			productId={productId}
			locations={locations}
			setInbound={setInbound}
			updateLocation={updateLocation}
			onBack={() => setActivePage(PAGES.HOME)}
			runAgentPipeline={runAgentPipeline}
			agentLoading={agentLoading}
			agentMessage={agentMessage}
			forecasts={forecasts}
			plan={plan}
		/>
	);
}
