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
	const [sampleLocations, setSampleLocations] = useState(defaultLocations);
	const [agentLocations, setAgentLocations] = useState([]);
	const [agentProductId, setAgentProductId] = useState("");
	const [inbound, setInbound] = useState(APP_CONFIG.defaultInbound);
	const [forecasts, setForecasts] = useState([]);
	const [plan, setPlan] = useState(null);

	const sampleProductId = APP_CONFIG.productId;

	const sampleActions = useWorkflowActions({
		productId: sampleProductId,
		inbound,
		locations: sampleLocations,
		setLocations: setSampleLocations,
		setForecasts,
		setPlan,
	});

	const agentActions = useWorkflowActions({
		productId: agentProductId,
		setProductId: setAgentProductId,
		inbound,
		locations: agentLocations,
		setLocations: setAgentLocations,
		setForecasts,
		setPlan,
	});

	const {
		sampleLoading,
		sampleMessage,
		forecastLoading,
		forecastMessage,
		runNotebookForecast,
		runSampleAllocation,
	} = sampleActions;

	const {
		agentLoading,
		agentMessage,
		bigCommerceLoading,
		bigCommerceMessage,
		runAgentPipeline,
		loadLocationsFromBigCommerce,
	} = agentActions;

	const activeLocations = activePage === PAGES.AGENT ? agentLocations : sampleLocations;

	const summary = useMemo(() => {
		const demand = activeLocations.reduce((acc, location) => acc + Number(location.demand_forecast || 0), 0);
		const onHand = activeLocations.reduce((acc, location) => acc + Number(location.inventory_level || 0), 0);
		return { demand, onHand };
	}, [activeLocations]);

	const updateSampleLocation = (locationId, field, value) => {
		setSampleLocations((prev) =>
			prev.map((location) =>
				location.location_id === locationId ? { ...location, [field]: value } : location
			)
		);
	};

	const updateAgentLocation = (locationId, field, value) => {
		setAgentLocations((prev) =>
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
				productId={sampleProductId}
				locations={sampleLocations}
				setInbound={setInbound}
				updateLocation={updateSampleLocation}
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
			productId={agentProductId}
			locations={agentLocations}
			setInbound={setInbound}
			updateLocation={updateAgentLocation}
			onBack={() => setActivePage(PAGES.HOME)}
			runAgentPipeline={runAgentPipeline}
			agentLoading={agentLoading}
			agentMessage={agentMessage}
			loadLocationsFromBigCommerce={loadLocationsFromBigCommerce}
			bigCommerceLoading={bigCommerceLoading}
			bigCommerceMessage={bigCommerceMessage}
			forecasts={forecasts}
			plan={plan}
		/>
	);
}
